import pytest

from app.db.repo_precos import carregar_tabela_precos
from scripts.migrar_catalogo_2026 import migrar

pytestmark = pytest.mark.db


def test_migracao_e_idempotente_rodando_2x(db):
    # `db` já chama aplicar_schema (schema novo) antes de cada teste; aqui
    # simulamos rodar a migração completa (schema + reseed) duas vezes
    # seguidas, como aconteceria em prod (contra um banco com schema antigo
    # na 1a vez e já migrado na 2a).
    c1 = migrar(db)
    c2 = migrar(db)
    assert c1 == c2 == {"categorias": 15, "itens": c1["itens"]}

    tabela = carregar_tabela_precos(db, "padrao")
    assert "tecnologia" in tabela.dados
    assert tabela.dados["tecnologia"]["_default"] == 22800

    mcmv = carregar_tabela_precos(db, "mcmv")
    assert mcmv.dados["internas"]["_default"] == 1500

    with db.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'propostas' AND column_name = 'tabela_precos'"
        )
        assert cur.fetchone() is not None
