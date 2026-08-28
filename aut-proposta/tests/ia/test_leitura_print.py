"""Leitura do print: prompt de extração e cache que evita reler a cada rodada."""
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


def test_prompt_leva_catalogo_e_regra_de_rigidez(tabela):
    prompt = leitura_print.montar_prompt(tabela)
    assert "CATÁLOGO OFICIAL" in prompt
    assert "externas" in prompt
    assert "REGRA DE RIGIDEZ" in prompt
    # Os quatro campos que importam e o balde de dúvidas.
    for rotulo in ("CONSTRUTORA", "EMPREENDIMENTO", "A/C", "ITENS", "DÚVIDAS"):
        assert rotulo in prompt


def test_le_o_print_uma_vez_e_reusa_do_cache(tabela, monkeypatch):
    chamadas = []
    monkeypatch.setattr(leitura_print, "_chamar_modelo",
                        lambda prompt, imgs: chamadas.append(imgs) or TRANSCRICAO)

    for _ in range(6):  # seis rodadas da mesma conversa, mesmo print
        assert leitura_print.transcrever([IMG], tabela) == TRANSCRICAO
    assert len(chamadas) == 1


def test_print_diferente_e_lido_de_novo(tabela, monkeypatch):
    chamadas = []
    monkeypatch.setattr(leitura_print, "_chamar_modelo",
                        lambda prompt, imgs: chamadas.append(imgs) or TRANSCRICAO)
    leitura_print.transcrever([IMG], tabela)
    leitura_print.transcrever([IMG2], tabela)
    assert len(chamadas) == 2


def test_cache_nao_cresce_sem_limite(tabela, monkeypatch):
    monkeypatch.setattr(leitura_print, "CACHE_MAX", 3)
    monkeypatch.setattr(leitura_print, "_chamar_modelo", lambda prompt, imgs: TRANSCRICAO)
    for i in range(10):
        leitura_print.transcrever([IMG._replace(hash=f"h{i}")], tabela)
    assert len(leitura_print._cache) == 3


def test_bloco_marca_a_transcricao_como_pedido_do_usuario():
    bloco = leitura_print.em_bloco(TRANSCRICAO)
    assert bloco.startswith(leitura_print.ABERTURA)
    assert TRANSCRICAO in bloco
    assert "DÚVIDAS" in bloco
