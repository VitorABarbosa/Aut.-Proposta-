"""Seções do roll, a regra de ambiente e o que muda de uma versão para a outra."""
import pytest

from app.dominio.roll import (
    classificar,
    diferenca,
    numerar,
    parece_tipologia,
    total_de_imagens,
)
from app.servicos.nomes import nome_do_roll

# Os 38 ambientes dos rolls reais (Ousy/Vila Mariana e Tavares/Pantojo), com a
# seção em que eles de fato saíram. É o gabarito da regra.
GABARITO = [
    ("externas", "Fachada noturna conceitual"),
    ("externas", "Fachada diurna"),
    ("externas", "Portaria de acesso"),
    ("externas", "Pet place"),
    ("externas", "Piscina"),
    ("externas", "Redário"),
    ("externas", "Web Garden"),
    ("externas", "Apoio Gourmet"),
    ("externas", "Fitness externo"),
    ("externas", "Fireplace"),
    ("externas", "Cine Open"),
    ("externas", "Lounge / Espelho d’água"),
    ("externas", "Voo Rooftop"),
    ("externas", "Solarium / Lounge"),
    ("externas", "Fotomontagem"),
    ("internas", "Lobby"),
    ("internas", "Delivery"),
    ("internas", "Locker"),
    ("internas", "Lavanderia"),
    ("internas", "Pet Care"),
    ("internas", "Coworking"),
    ("internas", "Podcast"),
    ("internas", "Gourmet"),
    ("internas", "Jogos"),
    ("internas", "Academia"),
    ("internas", "Jogos bar"),
    ("internas", "Studio"),
    ("internas", "Living Tipo 3"),
    ("internas", "Living – Tipo 2 (Studio)"),
    ("internas", "Bicicletário"),
    ("internas", "Salão de festas"),
    ("internas", "Fitness"),
    ("plantas", "Implantação do térreo"),
    ("plantas", "Implantação da cobertura"),
    ("plantas", "Implantação do pavimento (2º ao 12º)"),
    ("plantas", "Planta Studio Tipo 1 (2º ao 12º)"),
    ("plantas", "Planta 1 Dorm Tipo 2 (2º ao 12º)"),
    ("plantas", "Tipo 3 (2 Dormitórios)"),
    ("plantas", "Tipo 2 (Studio) - (variação de sacada)"),
]


@pytest.mark.parametrize("esperado,descricao", GABARITO)
def test_a_regra_acerta_os_ambientes_dos_rolls_reais(esperado, descricao):
    assert classificar(descricao) == esperado


def test_o_qualificador_ganha_do_ambiente():
    """"Fitness externo" e "Apoio Gourmet" moram na área externa mesmo tendo
    nome de sala — é o que os rolls dizem."""
    assert classificar("Fitness") == "internas"
    assert classificar("Fitness externo") == "externas"
    assert classificar("Gourmet") == "internas"
    assert classificar("Apoio Gourmet") == "externas"


def test_o_que_a_regra_nao_sabe_nao_e_chutado():
    """Item na seção errada é imagem cobrada errada lá na frente."""
    assert classificar("Sauna") is None
    assert classificar("Coisa que ninguém viu") is None
    assert classificar("") is None


def test_tipologia_com_nome_de_ambiente_e_planta_sem_virar_alarme():
    assert classificar("Tipo 2 (Studio)") == "plantas"
    assert parece_tipologia("Tipo 2 (Studio)")
    assert not parece_tipologia("Lobby")


def test_numeracao_e_escrita_na_hora():
    """Os rolls reais vêm com 2.1.1 num arquivo e 2.1 no outro; vale a ordem."""
    blocos = [{"tipo": "externas"}, {"tipo": "internas"}, {"tipo": "servico"}]
    assert [n for n, _ in numerar(blocos)] == ["2.1", "2.2", "2.3"]


def test_servico_nao_conta_como_imagem():
    blocos = [
        {"tipo": "externas", "itens": ["Fachada", "Piscina"]},
        {"tipo": "plantas", "itens": ["Implantação térreo"]},
        {"tipo": "servico", "titulo": "Maquete Eletrônica", "itens": ["Render 360°"]},
    ]
    assert total_de_imagens(blocos) == 3


def test_diferenca_entre_duas_versoes_do_roll():
    antes = [{"tipo": "externas", "itens": ["Fachada diurna", "Piscina"]},
             {"tipo": "plantas", "itens": ["Implantação térreo"]}]
    depois = [{"tipo": "externas", "itens": ["Fachada diurna", "Voo Rooftop"]},
              {"tipo": "plantas", "itens": ["Implantação térreo"]}]
    d = diferenca(antes, depois)
    assert [e["item"] for e in d["entrou"]] == ["Voo Rooftop"]
    assert [e["item"] for e in d["saiu"]] == ["Piscina"]
    assert (d["imagens_antes"], d["imagens_depois"]) == (3, 3)


def test_prefixo_de_escrita_nao_conta_como_mudanca():
    """Na atualização da Tavares os 11 ambientes internos ganharam
    "Perspectiva " na frente. Nada mudou — e o diff não pode dizer que sim."""
    antes = [{"tipo": "internas", "itens": ["Lobby", "Delivery"]}]
    depois = [{"tipo": "internas", "itens": ["Perspectiva Lobby", "Perspectiva Delivery"]}]
    d = diferenca(antes, depois)
    assert d["entrou"] == [] and d["saiu"] == []


def test_o_nome_da_versao():
    """"sempre salvamos como Roll_Flying -> Roll_Flying_Atl -> _Atl_1"."""
    assert [nome_do_roll("flying", v) for v in range(4)] == [
        "Roll_Flying", "Roll_Flying_Atl", "Roll_Flying_Atl_1", "Roll_Flying_Atl_2"]
    assert nome_do_roll("rinno", 1) == "Roll_Rinno_Atl"
    assert nome_do_roll("nid", 0) == "Roll_NID"
