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

from app.db.repo_precos import carregar_tabela_precos
from app.db.repo_propostas import listar_propostas, obter_estrutura_de_proposta
from app.dominio.precos import TabelaPrecos
from app.servicos.proposta import levantar

SAUDACAO = "Oi, tudo bem? O que vamos fazer hoje?"
QUICK_REPLIES = ["Nova proposta", "Consultar cliente", "Copiar proposta anterior"]
MSG_SEM_IA = ("O chat precisa da IA e ela está indisponível agora — "
              "use a aba 'Texto direto', que funciona sem internet da IA.")
MAX_RODADAS = 5

TABELAS_PRECOS = ("padrao", "mcmv")

_BASE_PROMPT = """Você é o assistente de propostas da Flying Studio. Tom descontraído,
direto e simpático, em português. Conduza a conversa para montar uma proposta:
precisa de construtora/incorporadora (cliente), empreendimento (ref), A/C (quem
recebe) e os itens — organizados pelas categorias do CATÁLOGO OFICIAL abaixo.
O usuário pode mandar tudo de uma vez ou aos poucos — pergunte SÓ o que faltar,
uma coisa por vez.

{catalogo}

REGRA DE RIGIDEZ: se o pedido não casar claramente com um item do catálogo
acima, NÃO classifique por palpite. Pergunte ao usuário qual item corresponde,
citando 2-3 candidatos do catálogo. Um serviço que não é imagem NUNCA entra
como ilustração externa/interna.

MCMV: se o usuário indicar que o empreendimento é Minha Casa Minha Vida
(MCMV/faixa/raiz), use tabela_precos='mcmv'. Na dúvida, pergunte.

REGRAS INEGOCIÁVEIS:
- Você NUNCA inventa nem calcula preço/valor. Todo número vem das ferramentas.
- Para precificar (mesmo parcial), chame precificar_proposta com a estrutura no
  formato: cliente = {{empresa, ref, contato}}; cada categoria do catálogo
  (nome entre parênteses acima, ex.: externas/internas/plantas/filmes/...) =
  lista de descrições de itens (uma string por unidade, repita a descrição se
  houver mais de uma unidade igual).
- Para consultar propostas antigas de um cliente, chame listar_propostas_cliente.
- Para copiar uma proposta mudando algo, chame carregar_proposta, ajuste a
  estrutura conforme o pedido e chame precificar_proposta.
- Depois de precificar, resuma os valores devolvidos e diga que o preview ao lado
  foi atualizado; se não houver pendências, diga que é só clicar em Gerar.

FORMATO DAS RESPOSTAS:
- Texto simples, SEM markdown: nada de **negrito**, títulos, tabelas ou colchetes
  de link. Frases curtas; se listar, use hífen simples no começo da linha.
- NUNCA inclua URLs ou links em nenhuma resposta. Para baixar uma proposta,
  oriente: "é só baixar na aba Histórico".
"""

# Mantido para compatibilidade/inspeção (catálogo vazio — prompt real é
# montado por `_montar_system_prompt` com o catálogo carregado do banco).
SYSTEM_PROMPT = _BASE_PROMPT.format(catalogo="CATÁLOGO OFICIAL (única fonte de classificação):")


def _montar_system_prompt(tabela: TabelaPrecos) -> str:
    """Injeta o catálogo oficial (rótulo + descrições, SEM preços) no prompt."""
    linhas = []
    for cat in tabela.categorias():
        meta = tabela.meta(cat)
        itens = tabela.dados[cat].get("tabela", [])
        descricoes = "; ".join(item["descricao"] for item in itens)
        linhas.append(f"- {meta['rotulo']} ({cat}): {descricoes}")
    catalogo = "CATÁLOGO OFICIAL (única fonte de classificação):\n" + "\n".join(linhas)
    return _BASE_PROMPT.format(catalogo=catalogo)


def _schema_estrutura(categorias: list[str]) -> dict:
    """Gera o JSON Schema da ferramenta precificar_proposta para as
    categorias ativas do catálogo (uma propriedade array-de-string por
    categoria) + tabela_precos (padrao|mcmv)."""
    properties: dict[str, Any] = {
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
    }
    for cat in categorias:
        properties[cat] = {
            "type": "array", "items": {"type": "string"},
            "description": f"Descrições dos itens da categoria '{cat}', uma entrada por unidade.",
        }
    properties["desconto_pct"] = {"type": "number", "description": "Percentual de desconto (0 se não houver)"}
    properties["desconto_label"] = {"type": ["string", "null"], "description": "Rótulo do desconto, se houver"}
    properties["estrategia"] = {"type": "string", "enum": ["planilha", "historico"],
                                 "description": "Fonte de preços a usar"}
    properties["tabela_precos"] = {"type": "string", "enum": list(TABELAS_PRECOS),
                                    "description": "Tabela de preços: 'padrao' ou 'mcmv' "
                                                   "(Minha Casa Minha Vida)."}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["cliente"],
    }


def _ferramentas(categorias: list[str]) -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": "precificar_proposta",
            "description": "Precifica a estrutura da proposta (preços oficiais/histórico). "
                           "Devolve valores, totais e pendências obrigatórias.",
            "parameters": {"type": "object", "properties": {"estrutura": _schema_estrutura(categorias)},
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


# Mantido para compatibilidade/inspeção — schema/ferramentas reais são
# montados por request em `responder`, com as categorias do catálogo carregado.
FERRAMENTAS = _ferramentas([])


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


_CATEGORIAS_FALLBACK = ("externas", "internas", "plantas")


def _completar_estrutura(bruto: dict, categorias: list[str] | None = None) -> dict:
    """Rede de segurança: completa a estrutura mandada pelo modelo com defaults,
    tolerando formatos levemente errados (ex.: cliente como string solta)."""
    categorias = list(categorias) if categorias is not None else list(_CATEGORIAS_FALLBACK)
    bruto = bruto or {}
    estrutura = {
        "cliente": {"empresa": "CLIENTE", "ref": "", "contato": ""},
        **{cat: [] for cat in categorias},
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
        "tabela_precos": "padrao",
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

    for chave in categorias:
        itens = estrutura.get(chave)
        if not isinstance(itens, list):
            itens = []
        estrutura[chave] = [str(item) for item in itens]

    if estrutura.get("tabela_precos") not in TABELAS_PRECOS:
        estrutura["tabela_precos"] = "padrao"

    return estrutura


def _executar_ferramenta(conn: psycopg.Connection, nome: str, args: dict,
                          categorias: list[str] | None = None) -> tuple[str, dict | None]:
    """Devolve (resultado_json_para_a_ia, levantamento_ou_None)."""
    if nome == "precificar_proposta":
        estrutura = _completar_estrutura(args.get("estrutura"), categorias)
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
        # Sem docx_url: o bucket é privado e a IA não deve citar links —
        # download é pela aba Histórico.
        propostas = [{k: v for k, v in p.items() if k != "docx_url"}
                     for p in listar_propostas(conn, args["cliente"])]
        return json.dumps(propostas, ensure_ascii=False), None
    if nome == "carregar_proposta":
        est = obter_estrutura_de_proposta(conn, int(args["proposta_id"]))
        return json.dumps(est, ensure_ascii=False), None
    return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), None


def responder(conn: psycopg.Connection, mensagens: list[dict]) -> dict[str, Any]:
    if not mensagens:
        return {"mensagem": SAUDACAO, "quick_replies": QUICK_REPLIES, "levantamento": None}
    if not os.getenv("OPENAI_API_KEY"):
        return {"mensagem": MSG_SEM_IA, "quick_replies": [], "levantamento": None}

    # Catálogo carregado 1x por request, fora do try/except abaixo (que só
    # cobre a conversa com o modelo): falha de banco deve propagar como nas
    # outras rotas, não virar MSG_SEM_IA silenciosamente.
    tabela = carregar_tabela_precos(conn)
    categorias = tabela.categorias()
    system_prompt = _montar_system_prompt(tabela)
    ferramentas = _ferramentas(categorias)

    llm: list[dict] = [{"role": "system", "content": system_prompt}] + list(mensagens)
    levantamento: dict | None = None
    try:
        for _ in range(MAX_RODADAS):
            msg = _chamar_modelo(llm, ferramentas)
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
                        conn, tc.function.name, json.loads(tc.function.arguments), categorias)
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
