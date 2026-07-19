"""Testes da API com TestClient. Banco real (fixture db); parser mockado onde útil."""
import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api.main import app
from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db

TOKEN = "token-de-teste"
HEAD = {"Authorization": f"Bearer {TOKEN}"}

TEXTO = """Cliente: GALLI, ref Residencial Aurora, a/c Daniel
Externas: Fachada vista da calçada
Internas: Academia
Plantas: Apartamento Tipo
10% de desconto, preço de planilha"""


@pytest.fixture
def cliente_api(db, tmp_path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("PROPOSTAS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # força parser local
    monkeypatch.setattr("app.servicos.proposta.enviar_docx", lambda c, k: None)
    aplicar_schema(db)
    semear_precos(db)
    # A API abre a própria conexão; aponta para o banco de teste.
    monkeypatch.setattr(api_main, "_abrir_conn", lambda: db)
    monkeypatch.setattr(api_main, "_fechar_conn", lambda conn: None)
    return TestClient(app)


def test_saude_sem_auth(cliente_api):
    r = cliente_api.get("/saude")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_sem_token_configurado_da_503(db, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    c = TestClient(app)
    r = c.post("/levantamento", json={"texto": "x"})
    assert r.status_code == 503


def test_token_errado_da_401(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": "x"},
                         headers={"Authorization": "Bearer errado"})
    assert r.status_code == 401


def test_token_errado_nao_ascii_da_401(cliente_api):
    # hmac.compare_digest em str crua explode com TypeError se o header tiver
    # caracteres não-ASCII; precisa comparar bytes. Header vai como bytes UTF-8
    # (httpx não aceita str não-ASCII direto em headers).
    r = cliente_api.post("/levantamento", json={"texto": "x"},
                         headers={"Authorization": "Bearer sënha-errada".encode("utf-8")})
    assert r.status_code == 401


def test_levantamento_precifica(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["estrutura"]["cliente"]["empresa"] == "GALLI"
    assert corpo["fechado"]["orcamento"]["externas"]["itens"][0]["preco"] == 3000
    assert corpo["fechado"]["financeiro"]["desconto_pct"] == 10.0
    assert corpo["estrategia_usada"] == "planilha"


def test_gerar_proposta_completa(cliente_api):
    r = cliente_api.post("/propostas", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    pid = corpo["proposta_id"]
    assert corpo["download"] == f"/propostas/{pid}/docx"
    assert corpo["docx_url"] is None  # R2 mockado como indisponível

    r2 = cliente_api.get(corpo["download"], headers=HEAD)
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert len(r2.content) > 1000  # docx de verdade


def test_gerar_por_estrutura_revisada(cliente_api):
    estrutura = {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    r = cliente_api.post("/propostas", json={"estrutura": estrutura}, headers=HEAD)
    assert r.status_code == 200
    assert r.json()["fechado"]["orcamento"]["subtotal"] == 3000


def test_levantamento_por_estrutura_reprecifica(cliente_api):
    estrutura = {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
        "desconto_pct": 5.0, "desconto_label": "ajuste", "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    r = cliente_api.post("/levantamento", json={"estrutura": estrutura}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["estrutura"]["cliente"]["empresa"] == "GALLI"
    assert corpo["fechado"]["orcamento"]["subtotal"] == 3000
    assert corpo["fechado"]["financeiro"]["desconto_pct"] == 5.0


def test_levantamento_sem_texto_nem_estrutura_422(cliente_api):
    r = cliente_api.post("/levantamento", json={}, headers=HEAD)
    assert r.status_code == 422


def test_pendencias_apontam_requisitos_faltantes(cliente_api):
    # Texto sem A/C e sem ref: parser preenche defaults, que contam como faltando.
    r = cliente_api.post("/levantamento", json={"texto": "Externas: Fachada"}, headers=HEAD)
    assert r.status_code == 200
    pend = r.json()["pendencias"]
    assert any("construtora" in p.lower() or "cliente" in p.lower() for p in pend)
    assert any("a/c" in p.lower() or "respons" in p.lower() for p in pend)
    assert any("empreendimento" in p.lower() or "projeto" in p.lower() for p in pend)


def test_pendencias_vazia_quando_completo(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    assert r.json()["pendencias"] == []


def test_pdf_de_proposta_inexistente_404(cliente_api):
    r = cliente_api.get("/propostas/99999/pdf", headers=HEAD)
    assert r.status_code == 404


def test_download_inexistente_404(cliente_api):
    r = cliente_api.get("/propostas/99999/docx", headers=HEAD)
    assert r.status_code == 404


def test_propostas_sem_texto_nem_estrutura_422(cliente_api):
    r = cliente_api.post("/propostas", json={}, headers=HEAD)
    assert r.status_code == 422


def test_pendencia_de_cliente_assumido_some_apos_edicao(cliente_api):
    """Regressão: a UI reenvia a estrutura com _avisos antigos; a pendência de
    cliente assumido só vale enquanto a empresa continuar sendo a assumida."""
    estrutura = {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada"], "internas": [], "plantas": [],
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False,
        "_avisos": ["Cliente não foi marcado explicitamente — assumi 'Externas: Fachada' (1ª linha)."],
    }
    r = cliente_api.post("/levantamento", json={"estrutura": estrutura}, headers=HEAD)
    assert r.status_code == 200
    pend = r.json()["pendencias"]
    # Empresa foi editada para GALLI (≠ valor assumido) -> não pode haver pendência de cliente.
    assert not any("construtora" in p.lower() for p in pend)

    # Mas se a empresa AINDA é o valor assumido, a pendência permanece.
    estrutura["cliente"]["empresa"] = "Externas: Fachada"
    r2 = cliente_api.post("/levantamento", json={"estrutura": estrutura}, headers=HEAD)
    assert any("construtora" in p.lower() for p in r2.json()["pendencias"])
