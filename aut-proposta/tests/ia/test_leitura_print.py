"""Leitura do print: as duas etapas (copiar, depois classificar) e o cache."""
from collections import OrderedDict

import pytest

from app.db.repo_precos import carregar_tabela_precos
from app.db.schema import aplicar_schema
from app.ia import leitura_print
from app.ia.visao import Imagem
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db

IMG = Imagem(url="data:image/jpeg;base64,AAAA", mime="image/jpeg", hash="abc123")
IMG2 = Imagem(url="data:image/jpeg;base64,BBBB", mime="image/jpeg", hash="def456")

LITERAL = """DE: Thais Bastos | Masha Coordenação de Projetos
PARA: Max Barbosa | Flying Studio
ASSUNTO: SAE - GUANAS | Proposta de Plano de Imagens
CORPO:
## O escopo previsto contempla:
1 Implantação 2º ao 13º Pavimento Tipo
## AMBIENTES INTERNOS - TÉRREO
Coworking
Hall"""

TRANSCRICAO = """CONSTRUTORA: GALLI
EMPREENDIMENTO: Aurora
A/C: Daniel
ITENS:
- externas | Fachada noturna | 3
DÚVIDAS:
- "umas internas do apto tipo" | candidatos: internas, plantas
OBSERVAÇÕES: nenhuma"""


@pytest.fixture
def tabela(db):
    aplicar_schema(db)
    semear_precos(db)
    return carregar_tabela_precos(db)


@pytest.fixture(autouse=True)
def cache_limpo(monkeypatch):
    monkeypatch.setattr(leitura_print, "_cache", OrderedDict())


@pytest.fixture
def duas_etapas(monkeypatch):
    """Substitui as duas chamadas ao modelo e guarda o que cada uma recebeu."""
    vistas, textos = [], []
    monkeypatch.setattr(leitura_print, "_chamar_modelo",
                        lambda prompt, imgs: vistas.append((prompt, imgs)) or LITERAL)
    monkeypatch.setattr(leitura_print, "_chamar_modelo_texto",
                        lambda prompt, txt: textos.append((prompt, txt)) or TRANSCRICAO)
    return vistas, textos


def test_prompt_de_classificacao_leva_catalogo_e_regra_de_rigidez(tabela):
    prompt = leitura_print.montar_prompt(tabela)
    assert "CATÁLOGO OFICIAL" in prompt
    assert "externas" in prompt
    assert "REGRA DE RIGIDEZ" in prompt
    # Os quatro campos que importam e o balde de dúvidas.
    for rotulo in ("CONSTRUTORA", "EMPREENDIMENTO", "A/C", "ITENS", "DÚVIDAS"):
        assert rotulo in prompt


def test_prompt_de_transcricao_so_manda_copiar(tabela):
    """Etapa 1 não pode ter catálogo: classificar enquanto lê é o que fazia o
    modelo resumir a lista e devolver 11 de 39 itens."""
    prompt = leitura_print.prompt_transcricao()
    assert "CATÁLOGO" not in prompt
    assert "COPIE TODAS AS LINHAS" in prompt
    assert "NÚMERO É SAGRADO" in prompt
    assert "CABEÇALHO DE SEÇÃO" in prompt
    # Nada de categoria nesta etapa.
    assert "externas" not in prompt and "plantas" not in prompt


def test_classificacao_recebe_a_transcricao_literal_e_nenhuma_imagem(tabela, duas_etapas):
    vistas, textos = duas_etapas
    assert leitura_print.transcrever([IMG], tabela) == TRANSCRICAO

    (prompt_visao, imgs), = vistas
    assert imgs == [IMG]
    assert prompt_visao == leitura_print.prompt_transcricao()

    (prompt_texto, entrada), = textos
    assert LITERAL in entrada          # a etapa 2 lê o que a etapa 1 copiou
    assert "CATÁLOGO OFICIAL" in prompt_texto


def test_secoes_e_faixas_de_andar_chegam_inteiras_na_classificacao(tabela, duas_etapas):
    _, textos = duas_etapas
    leitura_print.transcrever([IMG], tabela)
    entrada = textos[0][1]
    assert "## AMBIENTES INTERNOS - TÉRREO" in entrada
    assert "2º ao 13º Pavimento Tipo" in entrada


def test_le_o_print_uma_vez_e_reusa_do_cache(tabela, duas_etapas):
    vistas, textos = duas_etapas
    for _ in range(6):  # seis rodadas da mesma conversa, mesmo print
        assert leitura_print.transcrever([IMG], tabela) == TRANSCRICAO
    assert len(vistas) == 1 and len(textos) == 1


def test_print_diferente_e_lido_de_novo(tabela, duas_etapas):
    vistas, _ = duas_etapas
    leitura_print.transcrever([IMG], tabela)
    leitura_print.transcrever([IMG2], tabela)
    assert len(vistas) == 2


def test_cache_nao_cresce_sem_limite(tabela, monkeypatch):
    monkeypatch.setattr(leitura_print, "CACHE_MAX", 3)
    monkeypatch.setattr(leitura_print, "_chamar_modelo", lambda prompt, imgs: LITERAL)
    monkeypatch.setattr(leitura_print, "_chamar_modelo_texto", lambda prompt, txt: TRANSCRICAO)
    for i in range(10):
        leitura_print.transcrever([IMG._replace(hash=f"h{i}")], tabela)
    assert len(leitura_print._cache) == 3


def test_bloco_marca_a_transcricao_como_pedido_do_usuario():
    bloco = leitura_print.em_bloco(TRANSCRICAO)
    assert bloco.startswith(leitura_print.ABERTURA)
    assert TRANSCRICAO in bloco
    assert "DÚVIDAS" in bloco
    # O chat perdia itens ao reler a leitura; o fechamento cobra a lista inteira.
    assert "TODA linha de ITENS vira uma entrada" in bloco
