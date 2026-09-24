import pytest

from app.dominio.orcamento import orcar_pela_planilha, preco_final
from app.dominio.precos import TabelaPrecos
from tests.dominio.test_precos import DADOS


def tabela():
    return TabelaPrecos(DADOS)


def test_soma_por_categoria_e_subtotal():
    desc = {
        "externas": ["Fachada vista da calçada", "Jardim"],  # 3000 + 1900
        "internas": ["Academia", "Sauna"],                    # 1750 + 1750
        "plantas": ["Térreo"],                                # 3000
    }
    orc = orcar_pela_planilha(desc, tabela())
    assert orc.categorias["externas"].total == 4900
    assert orc.categorias["internas"].total == 3500
    assert orc.categorias["plantas"].total == 3000
    assert orc.subtotal == 11400
    assert orc.total_imagens == 5


def test_prefixa_descricao_padrao():
    orc = orcar_pela_planilha({"internas": ["Academia"]}, tabela())
    assert orc.categorias["internas"].itens[0].descricao_normalizada == "Perspectiva Academia"


def test_nao_duplica_prefixo_quando_usuario_ja_escreveu():
    orc = orcar_pela_planilha({"internas": ["Perspectiva Sauna"]}, tabela())
    assert orc.categorias["internas"].itens[0].descricao_normalizada == "Perspectiva Sauna"


def test_categoria_ausente_fica_vazia():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    assert orc.categorias["externas"].qtd == 0
    assert orc.categorias["plantas"].qtd == 0


def test_to_dict_tem_estrutura_esperada():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    d = orc.to_dict()
    assert d["estrategia"] == "planilha"
    assert d["subtotal"] == 1750
    assert d["internas"]["itens"][0]["preco"] == 1750


def test_to_dict_traz_categorias_meta_ordenada():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    d = orc.to_dict()
    assert d["_categorias"] == [
        {"nome": "externas", "rotulo": "Ilustrações Externas"},
        {"nome": "internas", "rotulo": "Ilustrações Internas"},
        {"nome": "plantas", "rotulo": "Plantas Humanizadas 2D"},
    ]


def test_orcamento_com_tour_e_tecnologia_soma_e_ordena():
    """A Flying não faz filme — o catálogo dela não tem a categoria."""
    real = TabelaPrecos()  # catálogo 2026 da Flying
    assert "filmes" not in real.categorias()
    desc = {
        "tour_virtual": ["Render 360"],
        "tecnologia": ["Aplicação Web Touch"],
    }
    orc = orcar_pela_planilha(desc, real)
    assert orc.categorias["tecnologia"].total == 22800
    assert orc.subtotal == 4150 + 22800

    nomes = [c["nome"] for c in orc.to_dict()["_categorias"]]
    assert nomes.index("tour_virtual") < nomes.index("tecnologia")


# ---------- serviço cobrado por ambiente ----------

# Catálogo de teste com a categoria cobrada por ambiente: três etapas do mesmo
# serviço, cada uma valendo por área de lazer. Sem prefixo de escrita, porque
# é serviço, não cena.
DADOS_TOUR = {
    **DADOS,
    "tour_virtual": {
        "_default": 1200, "_descricao_padrao": "Tour Virtual 360 — Render por ambiente",
        "_ordem": 9, "_rotulo": "Tour Virtual / VR 360", "_prefixo": "",
        "tabela": [
            {"chave": "tour_elaboracao", "descricao": "Tour Virtual — Elaboração, por ambiente",
             "preco": 2500, "padroes": ["elabora"]},
            {"chave": "tour_render", "descricao": "Tour Virtual — Render, por ambiente",
             "preco": 1200, "padroes": ["render"]},
            {"chave": "tour_web", "descricao": "Tour Virtual — Web/Mobile, por ambiente",
             "preco": 450, "padroes": ["web", "mobile"]},
        ],
    },
}


def tabela_tour():
    return TabelaPrecos(DADOS_TOUR)


def test_tour_virtual_multiplica_pela_quantidade_de_areas():
    """A regra da casa: o valor é proporcional à quantidade de áreas. Sete
    áreas de lazer custam 7x cada etapa (elaboração, render, web)."""
    preco, fonte = preco_final(2500, "tour_elaboracao", "tour_virtual", tabela_tour(),
                               ambientes=7)
    assert preco == 17500
    assert "x7 ambientes" in fonte


def test_sem_quantidade_o_tour_sai_por_um_ambiente():
    t = tabela_tour()
    assert preco_final(2500, "tour_elaboracao", "tour_virtual", t)[0] == 2500
    assert preco_final(2500, "tour_elaboracao", "tour_virtual", t, ambientes=1)[0] == 2500


def test_ambientes_nao_mexem_em_imagem():
    """Só a categoria cobrada por ambiente multiplica: fachada é uma cena, e
    cada ambiente do projeto de interiores da NID é uma entrada da lista."""
    assert preco_final(3000, "fachada", "externas", tabela_tour(), ambientes=7)[0] == 3000


def test_preco_informado_no_tour_e_o_valor_da_linha_inteira():
    """Quem fecha "a vista virtual por 25 mil" está fechando a linha, não a
    unidade — multiplicar viraria 175 mil."""
    preco, fonte = preco_final(2500, "tour_elaboracao", "tour_virtual", tabela_tour(),
                               preco_informado=25000, ambientes=7)
    assert (preco, fonte) == (25000, "informado")


def test_ajuste_de_planilha_e_ambientes_se_somam():
    preco, _ = preco_final(1000, "tour_render", "tour_virtual", tabela_tour(),
                           ajuste_pct=10, ambientes=3)
    assert preco == 3300  # 1000 +10% = 1100, x3 ambientes


def test_orcamento_inteiro_das_tres_etapas_por_sete_areas():
    """As sete áreas de lazer da proposta real: 7 x (2500 + 1200 + 450)."""
    orc = orcar_pela_planilha(
        {"tour_virtual": ["Elaboração 3d", "Render 360 VR", "Versão mobile offline"]},
        tabela_tour(), ambientes=7)
    assert orc.subtotal == 7 * (2500 + 1200 + 450)
    assert orc.to_dict()["ambientes"] == 7
