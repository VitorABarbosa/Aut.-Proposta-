import pytest

from app.dominio.precos import TabelaPrecos

# Tabela mínima em memória, espelhando a estrutura do JSON real.
DADOS = {
    "externas": {
        "_default": 1900,
        "_descricao_padrao": "Perspectiva Externa",
        "_ordem": 1, "_rotulo": "Ilustrações Externas", "_prefixo": "Perspectiva ",
        "tabela": [
            {"chave": "fachada", "descricao": "Perspectiva Fachada / Voo",
             "preco": 3000, "padroes": [r"\bfachada\b", "voo de passaro"]},
            {"chave": "externa_diversa", "descricao": "Perspectiva Externa",
             "preco": 1900, "padroes": [".*"]},
        ],
    },
    "internas": {
        "_default": 1750, "_descricao_padrao": "Perspectiva Interna",
        "_ordem": 2, "_rotulo": "Ilustrações Internas", "_prefixo": "Perspectiva ",
        "tabela": [{"chave": "interna_diversa", "descricao": "Perspectiva Interna",
                    "preco": 1750, "padroes": [".*"]}],
    },
    "plantas": {
        "_default": 1200, "_descricao_padrao": "Planta Humanizada",
        "_ordem": 3, "_rotulo": "Plantas Humanizadas 2D", "_prefixo": "Planta Humanizada ",
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
    # Não passa 'dados' -> deve carregar o catálogo 2026 (tabela padrao) do disco.
    t = TabelaPrecos()
    r = t.classificar("Perspectiva Sala", "internas")
    assert isinstance(r["preco"], int)


def test_categorias_ordenadas_por_ordem():
    assert tabela().categorias() == ["externas", "internas", "plantas"]


def test_meta_devolve_rotulo_prefixo_ordem():
    m = tabela().meta("plantas")
    assert m == {"rotulo": "Plantas Humanizadas 2D", "prefixo": "Planta Humanizada ", "ordem": 3}


def test_json_padrao_tem_8_categorias_incluindo_filmes_e_tecnologia():
    t = TabelaPrecos()
    nomes = t.categorias()
    assert len(nomes) == 8
    assert "filmes" in nomes and "tecnologia" in nomes
    # ordem determinística
    assert nomes == sorted(nomes, key=lambda c: t.meta(c)["ordem"])


def test_aplicacao_web_touch_classifica_em_tecnologia_22800():
    t = TabelaPrecos()
    r = t.classificar("Aplicação Web Touch", "tecnologia")
    assert r["chave"] == "app_web_touch"
    assert r["preco"] == 22800
