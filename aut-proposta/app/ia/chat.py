"""Chat conversacional da proposta: OpenAI com ferramentas internas.

A IA conduz a conversa (descontraída, pergunta o que falta, aceita tudo de
uma vez) e usa ferramentas para QUALQUER número: precificar, listar
propostas do cliente e carregar proposta antiga para copiar. Stateless — o
front manda o histórico inteiro a cada rodada.
"""
from __future__ import annotations

import json
import os
from typing import Any

import psycopg

from app.db.repo_propostas import listar_propostas, obter_estrutura_de_proposta
from app.servicos.proposta import levantar

SAUDACAO = "Oi, tudo bem? O que vamos fazer hoje?"
QUICK_REPLIES = ["Nova proposta", "Consultar cliente", "Copiar proposta anterior"]
MSG_SEM_IA = ("O chat precisa da IA e ela está indisponível agora — "
              "use a aba 'Texto direto', que funciona sem internet da IA.")
MAX_RODADAS = 5

SYSTEM_PROMPT = """Você é o assistente de propostas da Flying Studio. Tom descontraído,
direto e simpático, em português. Conduza a conversa para montar uma proposta:
precisa de construtora/incorporadora (cliente), empreendimento (ref), A/C (quem
recebe) e os itens (externas/internas/plantas). O usuário pode mandar tudo de uma
vez ou aos poucos — pergunte SÓ o que faltar, uma coisa por vez.

REGRAS INEGOCIÁVEIS:
- Você NUNCA inventa nem calcula preço/valor. Todo número vem das ferramentas.
- Para precificar (mesmo parcial), chame precificar_proposta com a estrutura no
  formato: cliente = {empresa, ref, contato}; externas/internas/plantas = listas
  de descrições de itens (uma string por unidade, repita a descrição se houver
  mais de uma unidade igual).
- Para consultar propostas antigas de um cliente, chame listar_propostas_cliente.
- Para copiar uma proposta mudando algo, chame carregar_proposta, ajuste a
  estrutura conforme o pedido e chame precificar_proposta.
- Depois de precificar, resuma os valores devolvidos e diga que o preview ao lado
  foi atualizado; se não houver pendências, diga que é só clicar em Gerar.
"""

_ESTRUTURA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cliente": {
            "type": "object",
            "description": "Dados do cliente da proposta.",
            "properties": {
                "empresa": {"type": "string", "description": "Construtora/incorporadora"},
                "ref": {"type": "string", "description": "Empreendimento/referência"},
                "contato": {"type": "string", "description": "A/C — quem recebe"},
            },
            "required": ["empresa"],
        },
        "externas": {
            "type": "array", "items": {"type": "string"},
            "description": "Descrições das imagens externas (ex.: 'Perspectiva Fachada'), "
                           "uma entrada por unidade.",
        },
        "internas": {
            "type": "array", "items": {"type": "string"},
            "description": "Descrições das imagens internas, uma entrada por unidade.",
        },
        "plantas": {
            "type": "array", "items": {"type": "string"},
            "description": "Descrições das plantas humanizadas, uma entrada por unidade.",
        },
        "desconto_pct": {"type": "number", "description": "Percentual de desconto (0 se não houver)"},
        "desconto_label": {"type": ["string", "null"], "description": "Rótulo do desconto, se houver"},
        "estrategia": {"type": "string", "enum": ["planilha", "historico"],
                       "description": "Fonte de preços a usar"},
    },
    "required": ["cliente"],
}

FERRAMENTAS = [
    {"type": "function", "function": {
        "name": "precificar_proposta",
        "description": "Precifica a estrutura da proposta (preços oficiais/histórico). "
                       "Devolve valores, totais e pendências obrigatórias.",
        "parameters": {"type": "object", "properties": {"estrutura": _ESTRUTURA_SCHEMA},
                       "required": ["estrutura"]}}},
    {"type": "function", "function": {
        "name": "listar_propostas_cliente",
        "description": "Lista as propostas já feitas para um cliente (id, projeto, data, total).",
        "parameters": {"type": "object", "properties": {"cliente": {"type": "string"}},
                       "required": ["cliente"]}}},
    {"type": "function", "function": {
        "name": "carregar_proposta",
        "description": "Carrega a estrutura completa de uma proposta antiga pelo id, "
                       "para copiar/ajustar e depois precificar.",
        "parameters": {"type": "object", "properties": {"proposta_id": {"type": "integer"}},
                       "required": ["proposta_id"]}}},
]


def _chamar_modelo(mensagens_llm: list[dict], tools: list[dict]):
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=mensagens_llm,
        tools=tools,
        temperature=0.4,
    )
    return resp.choices[0].message


def _completar_estrutura(bruto: dict) -> dict:
    """Rede de segurança: completa a estrutura mandada pelo modelo com defaults,
    tolerando formatos levemente errados (ex.: cliente como string solta)."""
    bruto = bruto or {}
    estrutura = {
        "cliente": {"empresa": "CLIENTE", "ref": "", "contato": ""},
        "externas": [], "internas": [], "plantas": [],
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    for chave, valor in bruto.items():
        estrutura[chave] = valor

    cliente = estrutura.get("cliente")
    if isinstance(cliente, str):
        cliente = {"empresa": cliente, "ref": "", "contato": ""}
    elif not isinstance(cliente, dict):
        cliente = {"empresa": "CLIENTE", "ref": "", "contato": ""}
    else:
        cliente = {"empresa": cliente.get("empresa") or "CLIENTE",
                   "ref": cliente.get("ref") or "",
                   "contato": cliente.get("contato") or ""}
    estrutura["cliente"] = cliente

    for chave in ("externas", "internas", "plantas"):
        itens = estrutura.get(chave)
        if not isinstance(itens, list):
            itens = []
        estrutura[chave] = [str(item) for item in itens]

    return estrutura


def _executar_ferramenta(conn: psycopg.Connection, nome: str, args: dict) -> tuple[str, dict | None]:
    """Devolve (resultado_json_para_a_ia, levantamento_ou_None)."""
    if nome == "precificar_proposta":
        estrutura = _completar_estrutura(args.get("estrutura"))
        lev = levantar(conn, estrutura)
        from app.api.main import _pendencias  # mesma regra de pendências da API
        lev_out = {
            "estrutura": estrutura,
            "fechado": lev["fechado"],
            "estrategia_usada": lev["estrategia_usada"],
            "avisos": lev["avisos"],
            "pendencias": _pendencias(estrutura, lev["fechado"]),
        }
        resumo = {
            "subtotal": lev["fechado"]["financeiro"]["subtotal"],
            "total": lev["fechado"]["financeiro"]["total"],
            "total_imagens": lev["fechado"]["orcamento"]["total_imagens"],
            "pendencias": lev_out["pendencias"],
            "avisos": lev["avisos"],
        }
        return json.dumps(resumo, ensure_ascii=False), lev_out
    if nome == "listar_propostas_cliente":
        return json.dumps(listar_propostas(conn, args["cliente"]), ensure_ascii=False), None
    if nome == "carregar_proposta":
        est = obter_estrutura_de_proposta(conn, int(args["proposta_id"]))
        return json.dumps(est, ensure_ascii=False), None
    return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), None


def responder(conn: psycopg.Connection, mensagens: list[dict]) -> dict[str, Any]:
    if not mensagens:
        return {"mensagem": SAUDACAO, "quick_replies": QUICK_REPLIES, "levantamento": None}
    if not os.getenv("OPENAI_API_KEY"):
        return {"mensagem": MSG_SEM_IA, "quick_replies": [], "levantamento": None}

    llm: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + list(mensagens)
    levantamento: dict | None = None
    try:
        for _ in range(MAX_RODADAS):
            msg = _chamar_modelo(llm, FERRAMENTAS)
            if not getattr(msg, "tool_calls", None):
                return {"mensagem": msg.content or "", "quick_replies": [],
                        "levantamento": levantamento}
            llm.append({"role": "assistant", "content": msg.content,
                        "tool_calls": [
                            {"id": tc.id, "type": "function",
                             "function": {"name": tc.function.name,
                                          "arguments": tc.function.arguments}}
                            for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                # Erro de ferramenta volta para a IA se corrigir na próxima
                # rodada; só falha de _chamar_modelo derruba para MSG_SEM_IA.
                try:
                    resultado, lev = _executar_ferramenta(
                        conn, tc.function.name, json.loads(tc.function.arguments))
                except Exception as exc:  # noqa: BLE001
                    resultado, lev = json.dumps(
                        {"erro": f"argumentos inválidos para {tc.function.name}: "
                                 f"{exc}. Corrija e tente de novo."},
                        ensure_ascii=False), None
                if lev is not None:
                    levantamento = lev
                llm.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
        return {"mensagem": "Precisei de muitas etapas — pode repetir de forma mais direta?",
                "quick_replies": [], "levantamento": levantamento}
    except Exception:  # noqa: BLE001 — IA indisponível nunca derruba o chat
        return {"mensagem": MSG_SEM_IA, "quick_replies": [], "levantamento": None}
