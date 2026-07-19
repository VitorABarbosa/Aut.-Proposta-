"""Testes do chat com o modelo mockado (sem rede)."""
import json
from types import SimpleNamespace

import pytest

from app.db.schema import aplicar_schema
from app.ia import chat
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(nome, argumentos, id_="tc1"):
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=nome, arguments=json.dumps(argumentos))
    )


ESTRUTURA = {
    "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
    "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
    "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
    "mostrar_precos_individuais": False, "_avisos": [],
}


def test_conversa_vazia_da_saudacao_sem_ia(db, monkeypatch):
    def _nunca(*a, **kw):
        raise AssertionError("não deveria chamar o modelo")
    monkeypatch.setattr(chat, "_chamar_modelo", _nunca)
    out = chat.responder(db, [])
    assert "Oi, tudo bem?" in out["mensagem"]
    assert out["quick_replies"] == ["Nova proposta", "Consultar cliente",
                                    "Copiar proposta anterior"]
    assert out["levantamento"] is None


def test_ia_precifica_via_ferramenta(db, monkeypatch):
    aplicar_schema(db)
    semear_precos(db)
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta", {"estrutura": ESTRUTURA})]),
        _msg(content="Fechado! Fachada da GALLI dá R$3.000,00. Gero a proposta?"),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    monkeypatch.setenv("OPENAI_API_KEY", "fake")

    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI, fachada"}])
    assert out["levantamento"] is not None
    assert out["levantamento"]["fechado"]["orcamento"]["subtotal"] == 3000
    assert "3.000" in out["mensagem"]


def test_sem_chave_nao_quebra(db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert "Texto direto" in out["mensagem"]
    assert out["levantamento"] is None


def test_excecao_do_modelo_nao_quebra(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    def _explode(*a, **kw):
        raise RuntimeError("api fora")
    monkeypatch.setattr(chat, "_chamar_modelo", _explode)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert out["levantamento"] is None
    assert "Texto direto" in out["mensagem"]
