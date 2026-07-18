import pytest

from app.db.repo_propostas import (
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
