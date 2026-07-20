import pytest

from app.db.repo_precos import carregar_tabela_precos
from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_carrega_categorias_novas_com_meta_e_ordem(db):
    aplicar_schema(db)
    semear_precos(db)

    tabela = carregar_tabela_precos(db)  # tabela="padrao" por padrão
    nomes = list(tabela.dados.keys())

    assert "filmes" in nomes
    assert "tecnologia" in nomes
    assert len(nomes) == 8  # as 8 categorias do catálogo 2026 (tabela padrao)

    # ordem determinística conforme a coluna `ordem`
    ordens = [tabela.dados[n]["_ordem"] for n in nomes]
    assert ordens == sorted(ordens)

    filmes = tabela.dados["filmes"]
    assert filmes["_rotulo"] == "Filmes e Takes 3D"
    assert filmes["_prefixo"] == ""
    assert filmes["_default"] == 15000
    assert filmes["_descricao_padrao"] == "Filme 3D — 60 segundos"

    tecnologia = tabela.dados["tecnologia"]
    assert tecnologia["_rotulo"] == "Tecnologias Interativas"
    assert any(
        item["chave"] == "app_web_touch" and item["preco"] == 22800
        for item in tecnologia["tabela"]
    )


def test_mcmv_carrega_precos_proprios(db):
    aplicar_schema(db)
    semear_precos(db)

    padrao = carregar_tabela_precos(db, "padrao")
    mcmv = carregar_tabela_precos(db, "mcmv")

    assert mcmv.dados["internas"]["_default"] == 1500
    assert padrao.dados["internas"]["_default"] == 1750

    # mcmv não tem "tecnologia" nem "estudos" com o mesmo preço da planilha padrão
    assert "tecnologia" not in mcmv.dados
    assert mcmv.dados["estudos"]["_default"] == 11500
    assert padrao.dados["estudos"]["_default"] == 18000


def test_ordem_preservada_primeiro_match_vence(db):
    aplicar_schema(db)
    semear_precos(db)
    tabela = carregar_tabela_precos(db)
    # "Fachada" tem que bater a linha de fachada (3000), não a diversa (1900).
    assert tabela.classificar("Fachada vista da calçada", "externas")["preco"] == 3000
