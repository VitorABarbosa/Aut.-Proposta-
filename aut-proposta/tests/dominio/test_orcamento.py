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
    assert orc.externas.total == 4900
    assert orc.internas.total == 3500
    assert orc.plantas.total == 3000
    assert orc.subtotal == 11400
    assert orc.total_imagens == 5


def test_prefixa_descricao_padrao():
    orc = orcar_pela_planilha({"internas": ["Academia"]}, tabela())
    assert orc.internas.itens[0].descricao_normalizada == "Perspectiva Academia"


def test_nao_duplica_prefixo_quando_usuario_ja_escreveu():
    orc = orcar_pela_planilha({"internas": ["Perspectiva Sauna"]}, tabela())
    assert orc.internas.itens[0].descricao_normalizada == "Perspectiva Sauna"


def test_categoria_ausente_fica_vazia():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    assert orc.externas.qtd == 0
    assert orc.plantas.qtd == 0


def test_to_dict_tem_estrutura_esperada():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    d = orc.to_dict()
    assert d["estrategia"] == "planilha"
    assert d["subtotal"] == 1750
    assert d["internas"]["itens"][0]["preco"] == 1750
