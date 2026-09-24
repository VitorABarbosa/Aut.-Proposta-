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

    assert "tour_virtual" in nomes
    assert "tecnologia" in nomes
    assert len(nomes) == 5  # a Flying faz imagem, planta, tour e tecnologia

    # ordem determinística conforme a coluna `ordem`
    ordens = [tabela.dados[n]["_ordem"] for n in nomes]
    assert ordens == sorted(ordens)

    tour = tabela.dados["tour_virtual"]
    assert tour["_rotulo"] == "Tour Virtual / VR 360"
    assert tour["_prefixo"] == ""
    assert tour["_default"] == 4150   # 2500 elaboração + 1200 render + 450 web

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

    # mcmv não tem "tecnologia" e tem preços próprios
    assert "tecnologia" not in mcmv.dados
    assert "tecnologia" not in mcmv.categorias()
    assert padrao.dados["tecnologia"]["_default"] == 22800


def test_ordem_preservada_primeiro_match_vence(db):
    aplicar_schema(db)
    semear_precos(db)
    tabela = carregar_tabela_precos(db)
    # "Fachada" tem que bater a linha de fachada (3000), não a diversa (1900).
    assert tabela.classificar("Fachada vista da calçada", "externas")["preco"] == 3000
