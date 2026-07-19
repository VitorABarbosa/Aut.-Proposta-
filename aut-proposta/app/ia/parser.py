"""Converte texto livre em estrutura de proposta (porte de flying/ai_parser.py).

Estratégia: com OPENAI_API_KEY tenta o modelo (json_object, temperatura 0) e
complementa lacunas com o parser regex local; sem chave ou em falha, o parser
local responde sozinho. A IA NUNCA vê nem produz preço — só nomes e listas.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

SECOES_CABEC = {
    "externas": [r"externas?", r"ilustra(?:c|ç)(?:o|õ)es externas", r"perspectivas externas",
                 r"imagens externas", r"\bext\b"],
    "internas": [r"internas?", r"ilustra(?:c|ç)(?:o|õ)es internas", r"perspectivas internas",
                 r"imagens internas", r"\bint\b"],
    "plantas": [r"plantas?", r"plantas? humanizadas?", r"plantas? baixas?",
                r"implanta(?:c|ç)(?:o|õ)es?"],
}

_RE_CLIENTE = re.compile(r"(?:^|\n|[,;.])\s*(?:cliente|empresa)\s*[:\-]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:ref|projeto|empreendimento|a/?c|contato|aos\s+cuidados))", re.I)
_RE_REF = re.compile(r"(?:^|\n|[,;.\-–—])\s*(?:ref(?:er[eê]ncia)?|projeto|empreendimento)\s*[:\-]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:cliente|empresa|a/?c|contato|aos\s+cuidados|\d+\s*%))", re.I)
_RE_CONTATO = re.compile(r"(?:^|\n|[,;.])\s*(?:a/?c|contato|aos\s+cuidados\s+de?)\s*[:\-\.]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:cliente|empresa|ref|projeto|empreendimento|\d+\s*%))", re.I)
_RE_DESCONTO = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*(?:de\s*)?(?:desconto|desc\.?|off)", re.I)
_RE_DESCONTO_2 = re.compile(r"desconto\s*(?:de|:)?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%", re.I)
_RE_ESTRATEGIA_PLAN = re.compile(r"\b(?:planilha|tabela\s*padr[aã]o|pre[cç]o\s*de\s*planilha|pre[cç]o\s*padr[aã]o)\b", re.I)
_RE_ESTRATEGIA_HIST = re.compile(r"\bhist[oó]ric|cliente\s*(?:antigo|anterior|recorrente)|m[eé]dia\s*do\s*cliente|mesma?\s*base\b", re.I)
_RE_PRECOS_IND = re.compile(r"pre[cç]os?\s*(?:individuais?|por\s*item|por\s*imagem)|coluna\s*de\s*(?:pre[cç]o|valor)", re.I)

_CAPS_IGNORAR = {"EXTERNAS", "INTERNAS", "PLANTAS", "REF", "PROJETO", "CLIENTE",
                 "EMPRESA", "DESCONTO", "HISTORICO", "HISTÓRICO", "PLANILHA", "TÉRREO"}


def _limpa_item(s: str) -> str:
    s = s.strip().strip(".;,")
    # Remove leading list markers (dashes, bullets) or numbered markers (e.g., "1. ", "1) ")
    # But preserve digits that are part of content (e.g., "10% de...")
    s = re.sub(r"^[\-\*•–—]+\s*", "", s)  # Remove bullet points
    s = re.sub(r"^\d+[\.\)]\s*", "", s)   # Remove numbered list markers like "1. " or "1) "
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _split_secoes(texto: str) -> dict[str, str]:
    matches: list[tuple[int, str, re.Match]] = []
    for cat, padroes in SECOES_CABEC.items():
        for pad in padroes:
            for m in re.finditer(rf"(?:^|\n|[\.;])\s*({pad})\s*[:\-]", texto, re.I):
                matches.append((m.start(), cat, m))
                break
    if not matches:
        return {}
    matches.sort(key=lambda x: x[0])
    blocos: dict[str, str] = {}
    for i, (_, cat, m) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(texto)
        blocos[cat] = texto[m.end():end].strip()
    return blocos


def _extrai_lista(bloco: str) -> list[str]:
    if not bloco:
        return []
    linhas = [l for l in bloco.splitlines() if l.strip()]
    if len(linhas) >= 2:
        items = [_limpa_item(l) for l in linhas if _limpa_item(l)]
        # Filtra itens que parecem ser metadata (desconto, estratégia, etc) ao invés de lista
        items = [i for i in items if not re.search(r"(?:desconto|planilha|histórico|histórico|preço)", i, re.I)]
        return items
    partes = re.split(r"[;,]| e ", bloco)
    return [_limpa_item(p) for p in partes if _limpa_item(p)]


def parse_local(texto: str) -> dict[str, Any]:
    avisos: list[str] = []
    if not texto.strip():
        avisos.append("Texto vazio.")

    cliente_match = _RE_CLIENTE.search(texto)
    ref_match = _RE_REF.search(texto)
    contato_match = _RE_CONTATO.search(texto)

    cliente = (cliente_match.group(1).strip() if cliente_match else "").rstrip(".;,")
    ref = (ref_match.group(1).strip() if ref_match else "").rstrip(".;,")
    contato = (contato_match.group(1).strip() if contato_match else "").rstrip(".;,")

    if not cliente and texto.strip():
        primeira = texto.strip().split("\n", 1)[0].strip()
        m_caps = re.match(
            r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9](?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 &]*[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])?)\b",
            primeira,
        )
        if m_caps and len(m_caps.group(1)) >= 3:
            cliente = m_caps.group(1).strip()
            avisos.append(f"Cliente não foi marcado explicitamente — assumi '{cliente}' (1as palavras em CAPS).")
            if not ref:
                resto = primeira[m_caps.end():].strip(" -–—:,.")
                resto = re.sub(r"^(?:ref(?:er[eê]ncia)?|projeto|empreendimento)\s*[:\-]?\s*", "", resto, flags=re.I)
                resto = re.sub(r"\b(?:a/?c|contato|aos\s+cuidados\s+de?)\b.*$", "", resto, flags=re.I).strip(" ,.")
                resto = re.sub(r",\s*\d+\s*%.*$", "", resto)
                if 2 <= len(resto) <= 60:
                    ref = resto
        else:
            m_any = re.search(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)?)\b", texto)
            if m_any and m_any.group(1) not in _CAPS_IGNORAR:
                cliente = m_any.group(1).strip()
                avisos.append(f"Cliente não foi marcado explicitamente — assumi '{cliente}' (palavra em CAPS no texto).")
            elif primeira and len(primeira) < 60:
                cliente = primeira
                avisos.append(f"Cliente não foi marcado explicitamente — assumi '{cliente}' (1ª linha).")

    desconto_pct = 0.0
    m = _RE_DESCONTO.search(texto) or _RE_DESCONTO_2.search(texto)
    if m:
        desconto_pct = float(m.group(1).replace(",", "."))

    estrategia = "auto"
    if _RE_ESTRATEGIA_PLAN.search(texto):
        estrategia = "planilha"
    elif _RE_ESTRATEGIA_HIST.search(texto):
        estrategia = "historico"

    blocos = _split_secoes(texto)
    externas = _extrai_lista(blocos.get("externas", ""))
    internas = _extrai_lista(blocos.get("internas", ""))
    plantas = _extrai_lista(blocos.get("plantas", ""))

    if texto.strip() and not (externas or internas or plantas):
        avisos.append("Não consegui identificar nenhuma seção (Externas/Internas/Plantas). "
                      "Use cabeçalhos tipo 'Externas:' seguidos de uma lista.")

    return {
        "cliente": {
            "empresa": cliente or "CLIENTE",
            "ref": ref or "PROJETO",
            "contato": contato or "—",
        },
        "externas": externas,
        "internas": internas,
        "plantas": plantas,
        "desconto_pct": desconto_pct,
        "desconto_label": None,
        "estrategia": estrategia,
        "mostrar_precos_individuais": bool(_RE_PRECOS_IND.search(texto)),
        "_origem": "local",
        "_avisos": avisos,
    }


SYSTEM_PROMPT = """Você é um assistente que converte descrições livres em português de
propostas comerciais da Flying Studio em JSON estruturado. Devolva APENAS JSON válido,
sem markdown, sem texto extra.

Schema:
{
  "cliente": {"empresa": "...", "ref": "...", "contato": "..."},
  "externas": ["nome do ambiente", ...],
  "internas": ["nome do ambiente", ...],
  "plantas":  ["nome", ...],
  "desconto_pct": 0,
  "desconto_label": null,
  "estrategia": "auto" | "planilha" | "historico",
  "mostrar_precos_individuais": false
}

Regras importantes:
- Se o usuário mencionou explicitamente "preço de planilha" ou "tabela padrão",
  estrategia = "planilha".
- Se mencionou "histórico do cliente" ou "preço médio do cliente" ou "mesma base
  do projeto anterior", estrategia = "historico".
- Caso contrário estrategia = "auto".
- Para imagens, mantenha o nome curto do ambiente (ex.: "Fachada", "Lobby",
  "Implantação Térreo"). NÃO prefixe com "Perspectiva" — o gerador faz isso.
- Se o usuário disser "10% de desconto", desconto_pct = 10.
- Se mencionar "preços individuais por imagem" ou "coluna de valor",
  mostrar_precos_individuais = true.
- NUNCA invente preços ou valores em reais.
"""


def _chamar_openai(texto: str) -> dict[str, Any] | None:
    """Chamada crua ao modelo. Devolve None sem OPENAI_API_KEY; propaga exceções."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    modelo = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=modelo,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": texto},
        ],
    )
    return json.loads(resp.choices[0].message.content or "{}")


def _preencher_defaults(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("_avisos", [])
    data.setdefault("desconto_label", None)
    data.setdefault("mostrar_precos_individuais", False)
    data.setdefault("estrategia", "auto")
    cli = data.setdefault("cliente", {})
    cli.setdefault("empresa", "CLIENTE")
    cli.setdefault("ref", "PROJETO")
    cli.setdefault("contato", "—")
    for k in ("externas", "internas", "plantas"):
        data.setdefault(k, [])
    data.setdefault("desconto_pct", 0)
    return data


def parse(texto: str) -> dict[str, Any]:
    """Tenta OpenAI; em falta de chave ou falha, usa o parser local."""
    texto = (texto or "").strip()
    if not texto:
        return parse_local("")

    aviso_falha = None
    try:
        bruto = _chamar_openai(texto)
    except Exception as exc:  # noqa: BLE001 — qualquer falha da API cai no local
        bruto = None
        aviso_falha = f"OpenAI indisponível, usando parser local. ({exc})"

    if bruto is not None:
        data = _preencher_defaults(bruto)
        data["_origem"] = "openai"
        # Complementa lacunas com o parser local (o modelo às vezes omite seções).
        local = parse_local(texto)
        for k in ("externas", "internas", "plantas"):
            if not data[k] and local[k]:
                data[k] = local[k]
        return data

    out = parse_local(texto)
    if aviso_falha:
        out["_avisos"].insert(0, aviso_falha)
    return out
