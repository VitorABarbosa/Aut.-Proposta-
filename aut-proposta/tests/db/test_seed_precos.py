import pytest

from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_seed_popula_categorias_e_itens(db):
    aplicar_schema(db)
    contagens = semear_precos(db)

    assert contagens["categorias"] == 3
    assert contagens["itens"] >= 3  # ao menos uma linha por categoria base

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM preco_categoria")
        assert cur.fetchone()[0] == 3
        # A categoria 'externas' deve conter a linha de fachada a 3000.
        cur.execute(
            "SELECT preco FROM preco_item WHERE categoria='externas' AND chave='fachada_fotomontagem_voo'"
        )
        assert cur.fetchone()[0] == 3000


def test_seed_e_idempotente(db):
    aplicar_schema(db)
    c1 = semear_precos(db)
    c2 = semear_precos(db)
    assert c1 == c2  # rodar duas vezes não duplica


def test_padroes_sao_lista(db):
    aplicar_schema(db)
    semear_precos(db)
    with db.cursor() as cur:
        cur.execute("SELECT padroes FROM preco_item WHERE categoria='externas' LIMIT 1")
        padroes = cur.fetchone()[0]
    assert isinstance(padroes, list)
