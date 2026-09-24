"""Roll exportado do Word se lê por regra: exato, de graça, sem chamar modelo."""
from app.ia.leitura_roll import arrumar, interpretar_texto

# Texto do Roll_Flying_Atl real (OUSY / Vila Mariana), como o pypdf o extrai.
ROLL_OUSY_ATL = """OUSY - REF: VILA MARIANA
2.1 – Ilustrações Externas
1. Fachada noturna conceitual
2. Fachada diurna
3. Portaria de acesso;
4. Pet place
5. Piscina
2.2 – Ilustrações Internas
1. Lobby
2. Delivery
3. Coworking
2.3 – Plantas Baixas
1. Implantação do térreo
2. Implantação do pavimento (2º ao 12º)
3. Planta Studio Tipo 1 (2º ao 12º)
2.4. Desenvolvimento Aplicação Web – Para Tela Touch
1. Catálogo Digital Interativo
2. Apresentação do Empreendimento
Aprovado em: 30 de Junho de 2026.
"""

# O primeiro roll do mesmo projeto: uma linha só, ainda sem detalhar.
ROLL_OUSY_INICIAL = """OUSY - REF: VILA MARIANA
2.1 Ilustrações Externas / Internas / Plantas Humanizadas 2D
1. 40 Perspectivas a Definir
Aprovado em: 30 de junho de 2026.
"""


def test_le_o_roll_inteiro_sem_perder_linha():
    roll = interpretar_texto(ROLL_OUSY_ATL)
    assert roll["cliente"] == {"empresa": "OUSY", "ref": "Vila Mariana"}
    assert roll["aprovado_em"] == "2026-06-30"
    assert [(b["tipo"], len(b["itens"])) for b in roll["blocos"]] == [
        ("externas", 5), ("internas", 3), ("plantas", 3), ("servico", 2)]
    assert roll["blocos"][0]["itens"][2] == "Portaria de acesso"   # sem o ";"
    assert roll["blocos"][2]["itens"][1] == "Implantação do pavimento (2º ao 12º)"
    assert roll["avisos"] == []


def test_as_secoes_escritas_no_roll_mandam():
    """Quem montou o roll decidiu onde cada ambiente entra — a regra não
    desmancha isso, só avisa."""
    roll = arrumar({"cliente": {"empresa": "X"}, "blocos": [
        {"tipo": "externas", "titulo": "Ilustrações Externas", "itens": ["Sauna", "Lobby"]},
    ]})
    assert roll["blocos"][0]["itens"] == ["Sauna", "Lobby"]
    assert any("Lobby" in a and "internas" in a for a in roll["avisos"])


def test_secao_que_mistura_as_tres_fica_para_confirmar():
    """"40 Perspectivas a Definir" debaixo de "Externas / Internas / Plantas"
    não é chutado para uma delas — e não pode sumir."""
    roll = interpretar_texto(ROLL_OUSY_INICIAL)
    assert [b["tipo"] for b in roll["blocos"]] == [""]
    assert roll["blocos"][0]["itens"] == ["40 Perspectivas a Definir"]
    assert roll["avisos"] and "não diz se é externa" in roll["avisos"][0]


def test_lista_colada_sem_secao_a_regra_divide():
    roll = arrumar({"cliente": {"empresa": "X"}, "blocos": [
        {"tipo": "", "titulo": "", "itens": ["Piscina", "Lobby", "Implantação térreo", "Sauna"]},
    ]})
    por_tipo = {b["tipo"]: b["itens"] for b in roll["blocos"]}
    assert por_tipo["externas"] == ["Piscina"]
    assert por_tipo["internas"] == ["Lobby"]
    assert por_tipo["plantas"] == ["Implantação térreo"]
    assert por_tipo[""] == ["Sauna"]


def test_secoes_saem_na_ordem_do_documento():
    roll = arrumar({"cliente": {"empresa": "X"}, "blocos": [
        {"tipo": "servico", "titulo": "Maquete Eletrônica", "itens": ["Render 360°"]},
        {"tipo": "plantas", "titulo": "", "itens": ["Implantação térreo"]},
        {"tipo": "externas", "titulo": "", "itens": ["Piscina"]},
    ]})
    assert [b["tipo"] for b in roll["blocos"]] == ["externas", "plantas", "servico"]


def test_secao_repetida_em_outra_pagina_vira_uma_so():
    roll = arrumar({"cliente": {"empresa": "X"}, "blocos": [
        {"tipo": "internas", "titulo": "Ilustrações Internas", "itens": ["Lobby"]},
        {"tipo": "internas", "titulo": "Ilustrações Internas (cont.)", "itens": ["Delivery"]},
    ]})
    assert len(roll["blocos"]) == 1
    assert roll["blocos"][0]["itens"] == ["Lobby", "Delivery"]


def test_texto_que_nao_e_roll_cai_no_modelo():
    assert interpretar_texto("oi, tudo bem? manda a proposta") is None
    assert interpretar_texto("") is None
