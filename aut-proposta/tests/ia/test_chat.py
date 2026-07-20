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


def test_ferramenta_com_erro_devolve_feedback_para_ia(db, monkeypatch):
    """Exceção numa ferramenta não mata a conversa: vira {"erro": ...} e a IA se corrige."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    historicos = []

    def _explode(*a, **kw):
        raise TypeError("shape errado")

    monkeypatch.setattr(chat, "levantar", _explode)
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta", {"estrutura": {"cliente": "GALLI"}})]),
        _msg(content="Opa, me faltou informação — qual o empreendimento?"),
    ]

    def _modelo(mensagens_llm, tools):
        historicos.append(list(mensagens_llm))
        return respostas.pop(0)

    monkeypatch.setattr(chat, "_chamar_modelo", _modelo)
    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI"}])
    assert out["mensagem"] == "Opa, me faltou informação — qual o empreendimento?"
    assert out["levantamento"] is None
    ultima_tool = [m for m in historicos[1] if m.get("role") == "tool"][-1]
    assert "erro" in ultima_tool["content"]


def test_estrutura_incompleta_e_completada(db, monkeypatch):
    """Estrutura parcial do modelo é completada com defaults antes de levantar."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta",
                                    {"estrutura": {"cliente": "GALLI",
                                                   "externas": ["Perspectiva Fachada"]}})]),
        _msg(content="Fechado! Deu R$3.000,00."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    out = chat.responder(db, [{"role": "user", "content": "GALLI, uma fachada"}])
    assert out["levantamento"] is not None
    assert out["levantamento"]["fechado"]["orcamento"]["subtotal"] > 0


def test_cliente_string_vira_objeto():
    est = chat._completar_estrutura({"cliente": "GALLI"})
    assert est["cliente"] == {"empresa": "GALLI", "ref": "", "contato": ""}
    assert est["externas"] == [] and est["desconto_pct"] == 0
    assert est["estrategia"] == "planilha" and est["_avisos"] == []


def test_schema_estrutura_contem_categorias_dinamicas():
    schema = chat._schema_estrutura(["externas", "internas", "plantas", "filmes", "tecnologia"])
    assert schema["properties"]["filmes"] == {
        "type": "array", "items": {"type": "string"},
        "description": "Descrições dos itens da categoria 'filmes', uma entrada por unidade.",
    }
    assert "tecnologia" in schema["properties"]
    assert schema["properties"]["tabela_precos"]["enum"] == ["padrao", "mcmv"]
    assert schema["additionalProperties"] is False


def test_completar_estrutura_preserva_tabela_precos_mcmv():
    est = chat._completar_estrutura({"cliente": "GALLI", "tabela_precos": "mcmv"})
    assert est["tabela_precos"] == "mcmv"


def test_completar_estrutura_tabela_precos_invalida_vira_padrao():
    est = chat._completar_estrutura({"cliente": "GALLI", "tabela_precos": "bitcoin"})
    assert est["tabela_precos"] == "padrao"


def test_completar_estrutura_categorias_dinamicas():
    est = chat._completar_estrutura({"filmes": ["Filme institucional"]}, ["filmes", "tecnologia"])
    assert est["filmes"] == ["Filme institucional"]
    assert est["tecnologia"] == []
    assert "externas" not in est


def test_montar_system_prompt_traz_catalogo_e_regra_rigidez(db):
    aplicar_schema(db)
    semear_precos(db)
    from app.db.repo_precos import carregar_tabela_precos
    tabela = carregar_tabela_precos(db)
    prompt = chat._montar_system_prompt(tabela)
    assert "REGRA DE RIGIDEZ" in prompt
    assert "Tecnologias Interativas" in prompt
    assert "MCMV" in prompt
    # Sem preços no catálogo injetado no prompt.
    assert "22800" not in prompt and "R$" not in prompt


def test_listar_para_ia_nao_expoe_docx_url(db, monkeypatch):
    """O bucket é privado: a IA não recebe docx_url (links são pela aba Histórico)."""
    monkeypatch.setattr(chat, "listar_propostas",
                        lambda conn, cliente: [{"id": 1, "cliente": "GALLI",
                                                "referencia": "Aurora", "data": "2026-07-19",
                                                "total": 3000.0,
                                                "docx_url": "https://r2/privado.docx"}])
    resultado, lev = chat._executar_ferramenta(db, "listar_propostas_cliente",
                                               {"cliente": "GALLI"})
    assert lev is None
    assert "docx_url" not in resultado and "r2/privado" not in resultado
    assert "GALLI" in resultado
