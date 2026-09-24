"""O nome com que o arquivo chega na mão do cliente."""
from app.servicos.nomes import com_revisao, nome_do_arquivo


def _orc(categoria: str, descricao: str, total: int = 1000, qtd: int = 1) -> dict:
    return {categoria: {"qtd": qtd, "total": total,
                        "itens": [{"descricao": descricao, "preco": total}]}}


def test_o_padrao_do_grupo():
    """"o arquivo tem sempre que vir salvo como
    Flying_Factus_Upside_Vista_AnexoI_R00"."""
    orc = _orc("tour_virtual", "Vista Virtual Web – Multiplataforma", 45000, 25)
    assert (nome_do_arquivo("flying", "Factus", "Upside", orc)
            == "Flying_Factus_Upside_Vista_AnexoI_R00")


def test_serviço_é_a_categoria_que_pesa_mais():
    """Proposta mista tem um nome só, e quem manda é o maior contrato."""
    orc = {**_orc("externas", "Perspectiva Fachada", 38000, 20),
           **_orc("tour_virtual", "Vista Virtual Web", 8300, 2)}
    assert "_Imagens_" in nome_do_arquivo("flying", "Casa Viva", "Guanás", orc)


def test_serviço_com_nome_próprio_vence_a_categoria():
    """Foi assim que as propostas saíram: Flying_D.sbrave_Elecon_Caieiras."""
    orc = _orc("tecnologia", "D.sbrave — Apartamento Modelo Virtual", 39000)
    assert (nome_do_arquivo("flying", "Elecon", "Caieiras", orc)
            == "Flying_Elecon_Caieiras_D.sbrave_AnexoI_R00")


def test_espaço_e_acento_somem_do_nome_do_arquivo():
    orc = _orc("nid_fachada", "Design de Fachada")
    assert (nome_do_arquivo("nid", "Tavares e Rosseti", "Pantojo Residência", orc)
            == "NID_TavaresERosseti_PantojoResidencia_Fachada_AnexoI_R00")


def test_sem_empreendimento_o_pedaço_some_em_vez_de_virar_underline_duplo():
    orc = _orc("rinno_filmes", "Filme Conceito", 19000)
    assert nome_do_arquivo("rinno", "Conviver", "", orc) == "Rinno_Conviver_Filmes_AnexoI_R00"


def test_revisao_com_dois_digitos():
    orc = _orc("plantas", "Planta Humanizada")
    assert nome_do_arquivo("flying", "Galli", "Aurora", orc, 3).endswith("_R03")
    assert nome_do_arquivo("flying", "Galli", "Aurora", orc, 12).endswith("_R12")


def test_com_revisao_preserva_o_nome_escrito_a_mao():
    assert com_revisao("Flying_Factus_Especial_R00", 1) == "Flying_Factus_Especial_R01"
    assert com_revisao("Proposta da Bruna", 2) == "Proposta da Bruna_R02"


def test_nome_escrito_a_mao_nao_vira_pasta_no_r2():
    from app.servicos.nomes import limpar

    assert limpar("../../etc/passwd") == "etcpasswd"
    assert limpar("Flying: Factus | R00") == "Flying Factus  R00"
