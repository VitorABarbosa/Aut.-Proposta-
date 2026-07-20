from app.dominio.orcamento import orcar_pela_planilha
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


def test_orcamento_com_filmes_e_tecnologia_soma_e_ordena():
    real = TabelaPrecos()  # catálogo 2026 completo (8 categorias)
    desc = {
        "filmes": ["Filme institucional 60 segundos"],
        "tecnologia": ["Aplicação Web Touch"],
    }
    orc = orcar_pela_planilha(desc, real)
    assert orc.categorias["filmes"].total == 15000
    assert orc.categorias["tecnologia"].total == 22800
    assert orc.subtotal == 15000 + 22800

    nomes = [c["nome"] for c in orc.to_dict()["_categorias"]]
    assert nomes.index("filmes") < nomes.index("tecnologia")
