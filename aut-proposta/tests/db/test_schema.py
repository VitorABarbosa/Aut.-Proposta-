import pytest

pytestmark = pytest.mark.db

TABELAS_ESPERADAS = {
    "preco_categoria", "preco_item", "clientes", "propostas", "proposta_itens",
}


def test_aplicar_schema_cria_todas_as_tabelas(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existentes = {r[0] for r in cur.fetchall()}
    assert TABELAS_ESPERADAS.issubset(existentes)


def test_aplicar_schema_e_idempotente(db):
    from app.db.schema import aplicar_schema

    # Chamar de novo não deve levantar erro.
    aplicar_schema(db)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM preco_categoria")
        assert cur.fetchone()[0] == 0
