import pytest

from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_seed_popula_categorias_e_itens_das_duas_tabelas(db):
    aplicar_schema(db)
    contagens = semear_precos(db)

    assert contagens["categorias"] == 15  # 8 (padrao) + 7 (mcmv)
    assert contagens["itens"] >= 15  # ao menos uma linha por categoria

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM preco_categoria WHERE tabela = 'padrao'")
        assert cur.fetchone()[0] == 8
        cur.execute("SELECT count(*) FROM preco_categoria WHERE tabela = 'mcmv'")
        assert cur.fetchone()[0] == 7

        # A categoria 'externas' padrão deve conter a linha de fachada a 3000.
        cur.execute(
            "SELECT preco FROM preco_item WHERE tabela='padrao' AND categoria='externas' AND chave='fachada'"
        )
        assert cur.fetchone()[0] == 3000

        # No mcmv a mesma chave 'fachada' tem preço próprio (2800).
        cur.execute(
            "SELECT preco FROM preco_item WHERE tabela='mcmv' AND categoria='externas' AND chave='fachada'"
        )
        assert cur.fetchone()[0] == 2800


def test_seed_e_idempotente(db):
    aplicar_schema(db)
    c1 = semear_precos(db)
    c2 = semear_precos(db)
    assert c1 == c2  # rodar duas vezes não duplica


def test_padroes_sao_lista(db):
    aplicar_schema(db)
    semear_precos(db)
    with db.cursor() as cur:
        cur.execute(
            "SELECT padroes FROM preco_item WHERE tabela='padrao' AND categoria='externas' LIMIT 1"
        )
        padroes = cur.fetchone()[0]
    assert isinstance(padroes, list)
