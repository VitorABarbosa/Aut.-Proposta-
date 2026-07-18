from app.dominio.descontos import Desconto
from app.dominio.orcamento import fechar_orcamento, orcar_pela_planilha
from app.dominio.precos import TabelaPrecos

# Caso real (proposta GALLI/Aiach): usa a tabela de preços REAL do JSON.
# 9 externas (2 fachadas a 3000 + 7 diversas a 1900) = 19300
# 5 internas a 1750 = 8750
# 4 plantas (3 implantação a 3000 + 1 tipo a 1200) = 10200
# subtotal = 38250 ; com 12% de desconto -> 33660
DESCRICOES = {
    "externas": [
        "Fachada vista da calçada", "Jardim", "Quadra de areia", "Piscina",
        "Dec c Jacuzzi", "Playground", "Gourmet churrasqueira",
        "Terraço rooftop", "Fachada Bird's View",
    ],
    "internas": ["Bicicletário", "Academia", "Sauna", "Brinquedoteca", "Salão de Festas"],
    "plantas": [
        "Implantação Térreo", "Implantação Mezanino lazer",
        "Implantação rooftop", "Apartamento Tipo",
    ],
}


def test_fechamento_caso_galli_com_desconto():
    orc = orcar_pela_planilha(DESCRICOES, TabelaPrecos())
    assert orc.subtotal == 38250

    fechado = fechar_orcamento(orc, Desconto("percentual", 12, "12% de Desconto de Parceria"))
    assert fechado["orcamento"]["subtotal"] == 38250
    assert fechado["financeiro"]["desconto_valor"] == 4590.0
    assert fechado["financeiro"]["total"] == 33660.0


def test_fechamento_sem_desconto():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, TabelaPrecos())
    fechado = fechar_orcamento(orc)
    assert fechado["financeiro"]["total"] == float(orc.subtotal)
