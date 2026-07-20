from pathlib import Path

import pytest

from app.db.repo_propostas import salvar_proposta, upsert_cliente
from app.db.schema import aplicar_schema
from app.servicos import proposta as svc
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _estrutura(estrategia="planilha", empresa="GALLI", desconto=0.0):
    return {
        "cliente": {"empresa": empresa, "ref": "Residencial Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"],
        "internas": ["Academia"],
        "plantas": ["Apartamento Tipo"],
        "desconto_pct": desconto,
        "desconto_label": "parceria" if desconto else None,
        "estrategia": estrategia,
        "mostrar_precos_individuais": False,
        "_avisos": [],
    }


def _prep(db):
    aplicar_schema(db)
    semear_precos(db)


def test_parse_texto_passa_categorias_do_catalogo_ao_parser(db, monkeypatch):
    _prep(db)
    recebido = {}

    def _parse_fake(texto, categorias=None):
        recebido["texto"] = texto
        recebido["categorias"] = categorias
        return {"cliente": {"empresa": "GALLI"}}

    monkeypatch.setattr("app.ia.parser.parse", _parse_fake)
    out = svc.parse_texto(db, "Cliente: GALLI\nFilmes: Filme institucional")
    assert out["cliente"]["empresa"] == "GALLI"
    assert "filmes" in recebido["categorias"]
    assert "tecnologia" in recebido["categorias"]


def test_levantar_planilha_precos_do_banco(db):
    _prep(db)
    out = svc.levantar(db, _estrutura())
    orc = out["fechado"]["orcamento"]
    assert out["estrategia_usada"] == "planilha"
    assert orc["externas"]["itens"][0]["preco"] == 3000  # fachada, preço do NEON
    assert orc["total_imagens"] == 3
    assert out["tabela_precos"] == "padrao"


def test_levantar_devolve_tabela_precos_padrao_por_default(db):
    _prep(db)
    out = svc.levantar(db, _estrutura())
    assert out["tabela_precos"] == "padrao"


def test_levantar_mcmv_precifica_interna_1500(db):
    _prep(db)
    est = _estrutura()
    est["tabela_precos"] = "mcmv"
    est["externas"] = []
    est["internas"] = ["Academia"]
    est["plantas"] = []
    out = svc.levantar(db, est)
    assert out["tabela_precos"] == "mcmv"
    assert out["fechado"]["orcamento"]["internas"]["itens"][0]["preco"] == 1500


def test_levantar_tabela_precos_invalida_levanta_erro(db):
    _prep(db)
    est = _estrutura()
    est["tabela_precos"] = "inexistente"
    with pytest.raises(ValueError):
        svc.levantar(db, est)


def test_levantar_com_desconto(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(desconto=10.0))
    fin = out["fechado"]["financeiro"]
    assert fin["desconto_pct"] == 10.0
    assert fin["total"] == pytest.approx(fin["subtotal"] * 0.9)
    assert fin["rotulo"] == "parceria"


def test_levantar_auto_usa_historico_quando_cliente_existe(db):
    _prep(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 1800, "total_imagens": 1,
            "externas": {"nome": "externas", "qtd": 0, "total": 0, "itens": []},
            "internas": {"nome": "internas", "qtd": 1, "total": 1800,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1800,
                                    "fonte": "manual"}]},
            "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []},
        },
        "financeiro": {"subtotal": 1800, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 1800.0, "rotulo": ""},
    })
    est = _estrutura(estrategia="auto", empresa="BRNPAR")
    est["externas"] = []
    est["plantas"] = []
    est["internas"] = ["Perspectiva Academia"]
    out = svc.levantar(db, est)
    assert out["estrategia_usada"].startswith("historico")
    assert out["fechado"]["orcamento"]["internas"]["itens"][0]["preco"] == 1800


def test_levantar_auto_sem_historico_cai_na_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="auto", empresa="CLIENTE NOVO"))
    assert out["estrategia_usada"] == "planilha"


def test_levantar_historico_sem_cliente_avisa_e_usa_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="historico", empresa="SEM HISTORICO"))
    assert out["estrategia_usada"] == "planilha"
    assert any("histórico" in a.lower() for a in out["avisos"])


def test_gerar_salva_docx_e_proposta(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)  # sem R2
    out = svc.gerar(db, _estrutura(desconto=10.0), tmp_path)

    assert out["proposta_id"] >= 1
    docx = Path(out["docx_path"])
    assert docx.exists() and docx.name == f"proposta_{out['proposta_id']}.docx"
    assert out["docx_url"] is None

    with db.cursor() as cur:
        cur.execute("SELECT subtotal, docx_url FROM propostas WHERE id = %s",
                    (out["proposta_id"],))
        subtotal, docx_url = cur.fetchone()
    assert subtotal == out["fechado"]["orcamento"]["subtotal"]
    assert docx_url is None


def test_gerar_com_r2_grava_url(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: f"https://r2.exemplo/{chave}")
    out = svc.gerar(db, _estrutura(), tmp_path)
    assert out["docx_url"] == f"https://r2.exemplo/{out['chave_r2']}"
    with db.cursor() as cur:
        cur.execute("SELECT docx_url FROM propostas WHERE id = %s", (out["proposta_id"],))
        assert cur.fetchone()[0] == out["docx_url"]


def test_gerar_persiste_apos_fechar_conexao(db, tmp_path, monkeypatch):
    """Regressão: os SELECTs de levantar abrem transação implícita e os
    conn.transaction() dos repos viram SAVEPOINTs — sem commit final, o
    close() da conexão descartava a proposta (visto na verificação real)."""
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    out = svc.gerar(db, _estrutura(), tmp_path)

    # Verifica numa SEGUNDA conexão: só enxerga o que foi de fato commitado.
    from tests.conftest import DSN_TESTE
    from app.db.conexao import get_conn

    outra = get_conn(DSN_TESTE)
    try:
        with outra.cursor() as cur:
            cur.execute("SELECT count(*) FROM propostas WHERE id = %s", (out["proposta_id"],))
            assert cur.fetchone()[0] == 1
    finally:
        outra.close()


def test_gerar_usa_chave_organizada_por_cliente_projeto(db, tmp_path, monkeypatch):
    _prep(db)
    chaves = []
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: (chaves.append(chave),
                                                f"https://r2/{chave}")[1])
    out = svc.gerar(db, _estrutura(), tmp_path)
    esperado = f"Propostas/galli/residencial-aurora/proposta_{out['proposta_id']}.docx"
    assert chaves == [esperado]
    assert out["chave_r2"] == esperado
