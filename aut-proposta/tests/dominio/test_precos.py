import pytest

from app.dominio.precos import TabelaPrecos

# Tabela mínima em memória, espelhando a estrutura do JSON real.
DADOS = {
    "externas": {
        "_default": 1900,
        "_descricao_padrao": "Perspectiva Externa",
        "tabela": [
            {"chave": "fachada", "descricao": "Perspectiva Fachada / Voo",
             "preco": 3000, "padroes": [r"\bfachada\b", "voo de passaro"]},
            {"chave": "externa_diversa", "descricao": "Perspectiva Externa",
             "preco": 1900, "padroes": [".*"]},
        ],
    },
    "internas": {
        "_default": 1750, "_descricao_padrao": "Perspectiva Interna",
        "tabela": [{"chave": "interna_diversa", "descricao": "Perspectiva Interna",
                    "preco": 1750, "padroes": [".*"]}],
    },
    "plantas": {
        "_default": 1200, "_descricao_padrao": "Planta Humanizada",
        "tabela": [
            {"chave": "implantacao", "descricao": "Planta Humanizada Implantação",
             "preco": 3000, "padroes": ["implantacao", "terreo"]},
            {"chave": "planta_tipo", "descricao": "Planta Humanizada Tipo",
             "preco": 1200, "padroes": [".*"]},
        ],
    },
}


def tabela():
    return TabelaPrecos(DADOS)


def test_classifica_fachada_como_3000():
    r = tabela().classificar("Fachada vista da calçada", "externas")
    assert r["chave"] == "fachada"
    assert r["preco"] == 3000


def test_externa_generica_cai_no_default():
    r = tabela().classificar("Perspectiva Jardim", "externas")
    assert r["preco"] == 1900


def test_planta_terreo_vira_implantacao():
    r = tabela().classificar("Planta Térreo", "plantas")
    assert r["preco"] == 3000


def test_categoria_invalida_levanta_erro():
    with pytest.raises(ValueError):
        tabela().classificar("qualquer", "filmes")


def test_carrega_json_padrao_quando_sem_dados():
    # Não passa 'dados' -> deve carregar o JSON real do disco sem erro.
    t = TabelaPrecos()
    r = t.classificar("Perspectiva Sala", "internas")
    assert isinstance(r["preco"], int)
