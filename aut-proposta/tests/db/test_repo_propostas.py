import pytest

from app.db.repo_propostas import (
    excluir_proposta,
    listar_propostas,
    obter_estrutura_de_proposta,
    salvar_proposta,
    ultima_proposta_estruturada,
    upsert_cliente,
)
from app.db.schema import aplicar_schema

pytestmark = pytest.mark.db


def _fechado_exemplo():
    # Espelha a estrutura de dominio.orcamento.fechar_orcamento.
    return {
        "orcamento": {
            "estrategia": "planilha",
            "subtotal": 5650,
            "total_imagens": 3,
            "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                         "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000, "fonte": "planilha:fachada"}]},
            "internas": {"nome": "internas", "qtd": 1, "total": 1750,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1750, "fonte": "planilha:interna_diversa"}]},
            "plantas": {"nome": "plantas", "qtd": 1, "total": 1200,
                        "itens": [{"descricao": "Planta Humanizada Tipo", "preco": 1200, "fonte": "planilha:planta_tipo"}]},
        },
        "financeiro": {"subtotal": 5650, "desconto_pct": 10.0, "desconto_valor": 565.0,
                       "total": 5085.0, "rotulo": "10% parceria"},
    }


def test_upsert_cliente_idempotente(db):
    aplicar_schema(db)
    id1 = upsert_cliente(db, "GALLI", "Daniel Pucci")
    id2 = upsert_cliente(db, "galli")  # mesmo cliente, caixa diferente
    assert id1 == id2


def test_salvar_proposta_grava_itens(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    pid = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Teste R00")

    with db.cursor() as cur:
        cur.execute("SELECT subtotal, total, desconto_pct FROM propostas WHERE id=%s", (pid,))
        subtotal, total, desconto_pct = cur.fetchone()
        assert subtotal == 5650
        assert float(total) == 5085.0
        assert float(desconto_pct) == 10.0
        cur.execute("SELECT count(*) FROM proposta_itens WHERE proposta_id=%s", (pid,))
        assert cur.fetchone()[0] == 3


def test_ultima_proposta_estruturada(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    salvar_proposta(db, cid, _fechado_exemplo())

    ult = ultima_proposta_estruturada(db, cid)
    assert ult["externas"]["qtd"] == 1
    assert ult["externas"]["total"] == 3000
    assert ult["externas"]["itens"][0] == {"desc": "Perspectiva Fachada", "preco": 3000}


def test_ultima_proposta_none_sem_proposta(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "NOVO CLIENTE")
    assert ultima_proposta_estruturada(db, cid) is None


def test_ultima_proposta_desempata_por_id_quando_mesma_data(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    salvar_proposta(db, cid, _fechado_exemplo())

    segunda = _fechado_exemplo()
    segunda["orcamento"]["externas"]["itens"][0]["preco"] = 4000
    segunda["orcamento"]["externas"]["total"] = 4000
    segunda["orcamento"]["subtotal"] = 6650
    segunda["financeiro"]["subtotal"] = 6650
    segunda["financeiro"]["total"] = 5985.0
    salvar_proposta(db, cid, segunda)

    ult = ultima_proposta_estruturada(db, cid)
    assert ult["externas"]["itens"][0] == {"desc": "Perspectiva Fachada", "preco": 4000}
    assert ult["externas"]["total"] == 4000


def test_obter_estrutura_de_proposta(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI", "Daniel")
    pid = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Residencial Aurora")

    estrutura = obter_estrutura_de_proposta(db, pid)
    assert estrutura is not None
    assert estrutura["cliente"]["empresa"] == "GALLI"
    assert estrutura["cliente"]["contato"] == "Daniel"
    assert estrutura["cliente"]["ref"] == "Residencial Aurora"
    assert estrutura["desconto_pct"] == 10.0
    assert len(estrutura["externas"]) == 1
    assert "Perspectiva Fachada" in estrutura["externas"]
    assert estrutura["estrategia"] == "planilha"
    assert estrutura["mostrar_precos_individuais"] is False


def test_obter_estrutura_proposta_nao_existe(db):
    aplicar_schema(db)
    assert obter_estrutura_de_proposta(db, 999) is None


def test_excluir_proposta(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    pid = salvar_proposta(db, cid, _fechado_exemplo())

    # Verifica que existe antes de apagar
    with db.cursor() as cur:
        cur.execute("SELECT id FROM propostas WHERE id = %s", (pid,))
        assert cur.fetchone() is not None

    # Apaga
    resultado = excluir_proposta(db, pid)
    assert resultado is True

    # Verifica que foi apagada
    with db.cursor() as cur:
        cur.execute("SELECT id FROM propostas WHERE id = %s", (pid,))
        assert cur.fetchone() is None
        cur.execute("SELECT count(*) FROM proposta_itens WHERE proposta_id = %s", (pid,))
        assert cur.fetchone()[0] == 0


def test_excluir_proposta_nao_existe(db):
    aplicar_schema(db)
    resultado = excluir_proposta(db, 999)
    assert resultado is False


def test_listar_propostas(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    pid1 = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Aurora")
    pid2 = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Aurora 2")

    propostas = listar_propostas(db, "GALLI")
    assert len(propostas) >= 2
    pids = [p["proposta_id"] for p in propostas]
    assert pid1 in pids and pid2 in pids
    # Verifica campos esperados
    for p in propostas:
        assert "proposta_id" in p
        assert "cliente" in p
        assert "referencia" in p
        assert "subtotal" in p
        assert "total" in p
        assert "download" in p


def test_listar_propostas_cliente_inexistente(db):
    aplicar_schema(db)
    propostas = listar_propostas(db, "CLIENTE NOVO")
    assert propostas == []
