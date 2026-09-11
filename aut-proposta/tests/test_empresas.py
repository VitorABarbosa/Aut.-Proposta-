"""Registro das três empresas do grupo e o cruzamento emissor × tabela."""
import pytest

from app.empresas import (
    EMISSOR_PADRAO,
    EMISSORES,
    empresa,
    emissor_da_tabela,
    resolver_tabela,
)


def test_as_tres_empresas_estao_registradas():
    assert EMISSORES == ("flying", "rinno", "nid")
    assert empresa("flying").nome == "FLYING STUDIO"
    assert empresa("rinno").nome == "RINNO FILMS"
    assert empresa("nid").nome == "NID STUDIO"


def test_cada_empresa_tem_o_seu_timbrado():
    timbrados = {empresa(c).timbrado for c in EMISSORES}
    assert len(timbrados) == 3
    for chave in EMISSORES:
        from app.docx.base import timbrado_de
        assert timbrado_de(empresa(chave)).exists(), chave


def test_emissor_vazio_cai_na_flying():
    """Proposta gravada antes do multi-empresa não tem emissor."""
    assert empresa(None).chave == EMISSOR_PADRAO
    assert empresa("").chave == "flying"


def test_emissor_aceita_maiuscula_e_espaco():
    assert empresa("  NID ").chave == "nid"


def test_emissor_desconhecido_e_erro():
    with pytest.raises(ValueError, match="emissor inválido"):
        empresa("disney")


def test_tabela_padrao_de_cada_empresa():
    assert resolver_tabela("flying", None) == "padrao"
    assert resolver_tabela("rinno", None) == "rinno"
    assert resolver_tabela("nid", None) == "nid"


def test_flying_aceita_mcmv():
    assert resolver_tabela("flying", "mcmv") == "mcmv"


def test_tabela_de_outra_empresa_e_recusada():
    """Pedir mcmv para a Rinno sairia como proposta errada no cliente."""
    with pytest.raises(ValueError, match="não é da RINNO FILMS"):
        resolver_tabela("rinno", "mcmv")
    with pytest.raises(ValueError, match="não é da NID STUDIO"):
        resolver_tabela("nid", "padrao")


def test_emissor_da_tabela_para_migrar_proposta_antiga():
    assert emissor_da_tabela("padrao") == "flying"
    assert emissor_da_tabela("mcmv") == "flying"
    assert emissor_da_tabela("rinno") == "rinno"
    assert emissor_da_tabela("nid") == "nid"
    assert emissor_da_tabela("tabela_que_nao_existe") == "flying"
