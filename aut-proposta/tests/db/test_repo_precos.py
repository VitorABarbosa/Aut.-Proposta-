import pytest

from app.db.repo_precos import carregar_tabela_precos
from app.db.schema import aplicar_schema
from app.dominio.precos import TabelaPrecos
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_tabela_do_banco_classifica_igual_ao_json(db):
    aplicar_schema(db)
    semear_precos(db)

    tabela_db = carregar_tabela_precos(db)
    tabela_json = TabelaPrecos()  # carrega o JSON direto

    # A classificação deve ser idêntica vindo do banco ou do JSON.
    for desc, cat in [
        ("Fachada vista da calçada", "externas"),
        ("Jardim", "externas"),
        ("Academia", "internas"),
        ("Implantação Térreo", "plantas"),
        ("Apartamento Tipo", "plantas"),
    ]:
        assert tabela_db.classificar(desc, cat) == tabela_json.classificar(desc, cat)


def test_ordem_preservada_primeiro_match_vence(db):
    aplicar_schema(db)
    semear_precos(db)
    tabela_db = carregar_tabela_precos(db)
    # "Fachada" tem que bater a linha de fachada (3000), não a diversa (1900).
    assert tabela_db.classificar("Fachada vista da calçada", "externas")["preco"] == 3000
