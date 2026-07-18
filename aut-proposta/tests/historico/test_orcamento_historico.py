import pytest

from app.db.repo_propostas import salvar_proposta, upsert_cliente
from app.db.schema import aplicar_schema
from app.historico.historico import Historico
from app.historico.orcamento_historico import orcar_pelo_historico
from app.dominio.precos import TabelaPrecos

pytestmark = pytest.mark.db

DADOS = {
    "externas": {"_default": 1900, "_descricao_padrao": "Perspectiva Externa",
                 "tabela": [{"chave": "externa_diversa", "descricao": "Perspectiva Externa",
                             "preco": 1900, "padroes": [".*"]}]},
    "internas": {"_default": 1750, "_descricao_padrao": "Perspectiva Interna",
                 "tabela": [{"chave": "interna_diversa", "descricao": "Perspectiva Interna",
                             "preco": 1750, "padroes": [".*"]}]},
    "plantas": {"_default": 1200, "_descricao_padrao": "Planta Humanizada",
                "tabela": [{"chave": "planta_tipo", "descricao": "Planta Humanizada Tipo",
                            "preco": 1200, "padroes": [".*"]}]},
}


def _proposta_premium():
    # Cliente que pagou premium: interna a 1800 (acima da tabela 1750).
    return {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 1800, "total_imagens": 1,
            "externas": {"nome": "externas", "qtd": 0, "total": 0, "itens": []},
            "internas": {"nome": "internas", "qtd": 1, "total": 1800,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1800, "fonte": "manual"}]},
            "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []},
        },
        "financeiro": {"subtotal": 1800, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 1800.0, "rotulo": ""},
    }


def test_sem_cliente_devolve_none(db):
    aplicar_schema(db)
    hist = Historico(db)
    assert orcar_pelo_historico(hist, "INEXISTENTE", {"internas": ["Academia"]}, TabelaPrecos(DADOS)) is None


def test_reaplica_preco_do_historico_item_exato(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, _proposta_premium())

    hist = Historico(db)
    orc = orcar_pelo_historico(hist, "BRNPAR", {"internas": ["Perspectiva Academia"]}, TabelaPrecos(DADOS))
    assert orc is not None
    assert orc.estrategia == "historico:BRNPAR"
    # Reaplica 1800 (histórico), não 1750 (tabela).
    assert orc.internas.itens[0].preco == 1800


def test_item_novo_cai_para_media_ou_planilha(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, _proposta_premium())

    hist = Historico(db)
    # Descrição de externas que o cliente nunca teve -> média (0 itens) -> planilha 1900.
    orc = orcar_pelo_historico(hist, "BRNPAR", {"externas": ["Jardim"]}, TabelaPrecos(DADOS))
    assert orc.externas.itens[0].preco == 1900
