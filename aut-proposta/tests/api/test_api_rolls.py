"""A aba do roll pela API: ler o que chegou, ver o que mudou, gerar a versão nova."""
import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api.main import app
from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db

TOKEN = "token-de-teste"
HEAD = {"Authorization": f"Bearer {TOKEN}"}

ROLL_INICIAL = """OUSY - REF: VILA MARIANA
2.1 – Ilustrações Externas
1. Fachada noturna conceitual
2. Fachada diurna
3. Piscina
2.2 – Ilustrações Internas
1. Lobby
2. Delivery
2.3 – Plantas Baixas
1. Implantação do térreo
Aprovado em: 30 de Junho de 2026.
"""

# O cliente cortou o Delivery, pediu o Voo Rooftop e escreveu "Perspectiva"
# na frente dos internos — que não é mudança nenhuma.
ROLL_ATUALIZADO = """OUSY - REF: VILA MARIANA
2.1 – Ilustrações Externas
1. Fachada noturna conceitual
2. Fachada diurna
3. Piscina
4. Voo Rooftop
2.2 – Ilustrações Internas
1. Perspectiva Lobby
2.3 – Plantas Baixas
1. Implantação do térreo
Aprovado em: 30 de Julho de 2026.
"""


@pytest.fixture
def cliente_api(db, tmp_path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("PROPOSTAS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.servicos.roll.enviar_docx", lambda c, k: None)
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setattr(api_main, "_abrir_conn", lambda: db)
    monkeypatch.setattr(api_main, "_fechar_conn", lambda conn: None)
    return TestClient(app)


def _ler(cliente_api, texto):
    r = cliente_api.post("/rolls/leitura", json={"texto": texto}, headers=HEAD)
    assert r.status_code == 200, r.text
    return r.json()["roll"]


def test_le_o_roll_colado_e_devolve_as_secoes(cliente_api):
    roll = _ler(cliente_api, ROLL_INICIAL)
    assert roll["cliente"] == {"empresa": "OUSY", "ref": "Vila Mariana"}
    assert [(b["tipo"], len(b["itens"])) for b in roll["blocos"]] == [
        ("externas", 3), ("internas", 2), ("plantas", 1)]


def test_o_primeiro_roll_do_projeto_e_o_Roll_Flying(cliente_api):
    roll = _ler(cliente_api, ROLL_INICIAL)
    corpo = cliente_api.post("/rolls", json={"roll": roll, "emissor": "flying"},
                             headers=HEAD).json()
    assert corpo["versao"] == 0
    assert corpo["nome_arquivo"] == "Roll_Flying"
    assert corpo["imagens"] == 6
    assert corpo["mudou"] is None     # não há versão anterior com que comparar

    r = cliente_api.get(corpo["download"], headers=HEAD)
    assert r.status_code == 200
    assert "Roll_Flying.docx" in r.headers["content-disposition"]


def test_a_versao_seguinte_vira_Atl_e_diz_o_que_mudou(cliente_api):
    """É a pergunta que se faz todo vez que um roll novo chega: o que entrou,
    o que saiu."""
    cliente_api.post("/rolls", json={"roll": _ler(cliente_api, ROLL_INICIAL)},
                     headers=HEAD)
    corpo = cliente_api.post("/rolls", json={"roll": _ler(cliente_api, ROLL_ATUALIZADO)},
                             headers=HEAD).json()

    assert corpo["versao"] == 1
    assert corpo["nome_arquivo"] == "Roll_Flying_Atl"
    assert corpo["anterior"]["nome_arquivo"] == "Roll_Flying"

    mudou = corpo["mudou"]
    assert [e["item"] for e in mudou["entrou"]] == ["Voo Rooftop"]
    assert [e["item"] for e in mudou["saiu"]] == ["Delivery"]
    # "Perspectiva Lobby" é o mesmo Lobby de antes: não entra nem sai.
    assert (mudou["imagens_antes"], mudou["imagens_depois"]) == (6, 6)


def test_a_terceira_versao_e_Atl_1(cliente_api):
    for texto in (ROLL_INICIAL, ROLL_ATUALIZADO, ROLL_INICIAL):
        corpo = cliente_api.post("/rolls", json={"roll": _ler(cliente_api, texto)},
                                 headers=HEAD).json()
    assert corpo["versao"] == 2
    assert corpo["nome_arquivo"] == "Roll_Flying_Atl_1"


def test_cada_empresa_tem_a_sua_sequencia_de_roll(cliente_api):
    """"não apenas da flying temos roll" — o mesmo projeto pode ter roll das
    três, e a versão de uma não conta para a outra."""
    roll = _ler(cliente_api, ROLL_INICIAL)
    flying = cliente_api.post("/rolls", json={"roll": roll, "emissor": "flying"},
                              headers=HEAD).json()
    rinno = cliente_api.post("/rolls", json={"roll": roll, "emissor": "rinno"},
                             headers=HEAD).json()
    assert flying["nome_arquivo"] == "Roll_Flying"
    assert rinno["nome_arquivo"] == "Roll_Rinno"
    assert rinno["versao"] == 0


def test_o_historico_lista_os_rolls_com_a_contagem_de_imagens(cliente_api):
    cliente_api.post("/rolls", json={"roll": _ler(cliente_api, ROLL_INICIAL)}, headers=HEAD)
    cliente_api.post("/rolls", json={"roll": _ler(cliente_api, ROLL_ATUALIZADO)}, headers=HEAD)
    lista = cliente_api.get("/rolls", headers=HEAD).json()["rolls"]
    assert [r["nome_arquivo"] for r in lista] == ["Roll_Flying_Atl", "Roll_Flying"]
    assert [r["imagens"] for r in lista] == [6, 6]
    assert lista[0]["referencia"] == "Vila Mariana"


def test_roll_volta_inteiro_para_editar_e_some_quando_excluido(cliente_api):
    corpo = cliente_api.post("/rolls", json={"roll": _ler(cliente_api, ROLL_INICIAL)},
                             headers=HEAD).json()
    rid = corpo["roll_id"]

    volta = cliente_api.get(f"/rolls/{rid}", headers=HEAD).json()
    assert volta["estrutura"]["blocos"][0]["itens"][0] == "Fachada noturna conceitual"
    assert volta["versao"] == 0

    assert cliente_api.delete(f"/rolls/{rid}", headers=HEAD).status_code == 200
    assert cliente_api.get(f"/rolls/{rid}", headers=HEAD).status_code == 404
    assert cliente_api.get(f"/rolls/{rid}/docx", headers=HEAD).status_code == 404


def test_roll_sem_cliente_e_erro_de_entrada_e_nao_500(cliente_api):
    r = cliente_api.post("/rolls", json={"roll": {"cliente": {}, "blocos": [
        {"tipo": "externas", "itens": ["Piscina"]}]}}, headers=HEAD)
    assert r.status_code == 422 and "cliente" in r.json()["detail"]


def test_leitura_sem_nada_pede_o_roll(cliente_api):
    r = cliente_api.post("/rolls/leitura", json={"texto": "  "}, headers=HEAD)
    assert r.status_code == 422 and "roll" in r.json()["detail"].lower()


def test_pdf_ilegivel_e_erro_de_entrada_e_nao_500(cliente_api):
    r = cliente_api.post("/rolls/leitura", json={"pdfs": ["isso-nao-e-um-pdf"]}, headers=HEAD)
    assert r.status_code == 422 and "PDF" in r.json()["detail"]
