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

CATEGORIAS_FALLBACK = ("externas", "internas", "plantas")

_SECOES_CABEC_ESPECIAIS = {
    "externas": [r"externas?", r"ilustra(?:c|ç)(?:o|õ)es externas", r"perspectivas externas",
                 r"imagens externas", r"\bext\b"],
    "internas": [r"internas?", r"ilustra(?:c|ç)(?:o|õ)es internas", r"perspectivas internas",
                 r"imagens internas", r"\bint\b"],
    "plantas": [r"plantas?", r"plantas? humanizadas?", r"plantas? baixas?",
                r"implanta(?:c|ç)(?:o|õ)es?"],
}


def _secoes_cabec(categorias: list[str] | tuple[str, ...]) -> dict[str, list[str]]:
    """Gera os padrões de cabeçalho de seção por categoria.

    Para as 3 categorias históricas mantém os sinônimos já existentes; para
    categorias novas (vindas do catálogo dinâmico), usa o nome da categoria
    aceitando espaço no lugar de "_" (ex.: "tour_virtual" reconhece
    "Tour Virtual:").
    """
    secoes: dict[str, list[str]] = {}
    for cat in categorias:
        if cat in _SECOES_CABEC_ESPECIAIS:
            secoes[cat] = list(_SECOES_CABEC_ESPECIAIS[cat])
        else:
            # Categoria de outra empresa vem com prefixo (`rinno_filmes`,
            # `nid_fachada`), mas ninguém escreve "Rinno filmes:" no pedido —
            # escreve "Filmes:". O cabeçalho é o nome sem o prefixo; o nome
            # completo continua valendo.
            sem_prefixo = _sem_prefixo_de_emissor(cat)
            padroes = [rf"{re.escape(sem_prefixo.replace('_', ' '))}s?"]
            if sem_prefixo != cat:
                padroes.append(rf"{re.escape(cat.replace('_', ' '))}s?")
            secoes[cat] = padroes
    return secoes


def _sem_prefixo_de_emissor(cat: str) -> str:
    from app.empresas import EMISSORES

    for emissor in EMISSORES:
        if cat.startswith(f"{emissor}_"):
            return cat[len(emissor) + 1:]
    return cat


# Mantido para compatibilidade/inspeção: padrões das 3 categorias históricas.
SECOES_CABEC = _secoes_cabec(CATEGORIAS_FALLBACK)

_RE_CLIENTE = re.compile(r"(?:^|\n|[,;.])\s*(?:cliente|empresa)\s*[:\-]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:ref|projeto|empreendimento|a/?c|contato|aos\s+cuidados))", re.I)
_RE_REF = re.compile(r"(?:^|\n|[,;.\-–—])\s*(?:ref(?:er[eê]ncia)?|projeto|empreendimento)\s*[:\-]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:cliente|empresa|a/?c|contato|aos\s+cuidados|\d+\s*%))", re.I)
_RE_CONTATO = re.compile(r"(?:^|\n|[,;.])\s*(?:a/?c|contato|aos\s+cuidados\s+de?)\s*[:\-\.]?\s+([^\n,;.]+?)(?=$|\n|[,;]|\.\s|\s+(?:cliente|empresa|ref|projeto|empreendimento|\d+\s*%))", re.I)
_RE_DESCONTO = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*(?:de\s*)?(?:desconto|desc\.?|off)", re.I)
_RE_DESCONTO_2 = re.compile(r"desconto\s*(?:de|:)?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%", re.I)
_RE_ESTRATEGIA_PLAN = re.compile(r"\b(?:planilha|tabela\s*padr[aã]o|pre[cç]o\s*de\s*planilha|pre[cç]o\s*padr[aã]o)\b", re.I)
_RE_ESTRATEGIA_HIST = re.compile(r"\bhist[oó]ric|cliente\s*(?:antigo|anterior|recorrente)|m[eé]dia\s*do\s*cliente|mesma?\s*base\b", re.I)
# "planilha + 10%", "planilha mais 10%", "10% em cima", "acréscimo de 10%"
_RE_AJUSTE_POS = re.compile(
    r"planilha\s*(?:\+|mais|com)\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%"
    r"|(\d{1,3}(?:[.,]\d{1,2})?)\s*%\s*(?:em\s*cima|a\s*mais|de\s*acr[eé]scimo)"
    r"|acr[eé]scimo\s*(?:de)?\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%", re.I)
# "planilha - 5%", "planilha menos 5%"
_RE_AJUSTE_NEG = re.compile(r"planilha\s*(?:-|menos)\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%", re.I)
# "2.400 por imagem", "R$ 2200 a imagem", "média de 2.200 por imagem"
_RE_PRECO_IMAGEM = re.compile(
    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d{3,6})(?:,\d{2})?\s*(?:reais\s*)?(?:por|a|cada|/)\s*imagem", re.I)
# "7 ambientes", "7 áreas de lazer", "sete áreas": a quantidade que multiplica
# o tour virtual. Só o número em algarismo — por extenso é pergunta, não palpite.
_RE_AMBIENTES = re.compile(
    r"(\d{1,2})\s*(?:ambientes?|[aá]reas?(?:\s+de\s+lazer)?)\b", re.I)
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


def _split_secoes(texto: str, categorias: list[str] | tuple[str, ...] | None = None) -> dict[str, str]:
    categorias = list(categorias) if categorias is not None else list(CATEGORIAS_FALLBACK)
    secoes_cabec = _secoes_cabec(categorias)
    matches: list[tuple[int, str, re.Match]] = []
    for cat, padroes in secoes_cabec.items():
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


# "Filme institucional de 2:00 = 15.000", "Filme conceito por 15 mil",
# "Viral - R$ 4.500". Separador ":" fica de fora de propósito: "2:00" é duração.
_RE_ITEM_COM_PRECO = re.compile(
    r"^(?P<desc>.+?)\s*(?:=|\s[-–]\s|\bpor\b|R\$)\s*R?\$?\s*"
    r"(?P<valor>\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?\s*(?P<mil>mil|k)?\s*(?:reais)?\s*$", re.I)


def _item_com_preco(item: str) -> str | dict[str, Any]:
    """Item que termina em valor vira {descricao, preco}; o resto fica texto."""
    m = _RE_ITEM_COM_PRECO.match(item)
    if not m:
        return item
    valor = int(m.group("valor").replace(".", ""))
    if m.group("mil"):
        valor *= 1000
    if valor < 50:  # "Fachada - 2" não é preço
        return item
    return {"descricao": m.group("desc").strip(), "preco": valor}


def _extrai_lista(bloco: str) -> list:
    if not bloco:
        return []
    linhas = [l for l in bloco.splitlines() if l.strip()]
    if len(linhas) >= 2:
        items = [_limpa_item(l) for l in linhas if _limpa_item(l)]
    else:
        partes = re.split(r"[;,]| e ", bloco)
        items = [_limpa_item(p) for p in partes if _limpa_item(p)]
    # Filtra itens que parecem ser metadata (desconto, estratégia, etc) ao invés de lista
    items = [i for i in items if not re.search(
        r"(?:desconto|planilha|hist[oó]rico|pre[cç]o|acr[eé]scimo|(?:por|a|cada)\s*imagem)", i, re.I)]
    return [_item_com_preco(i) for i in items]


def parse_local(texto: str, categorias: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    categorias = list(categorias) if categorias is not None else list(CATEGORIAS_FALLBACK)
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

    ajuste_pct = 0.0
    m = _RE_AJUSTE_POS.search(texto)
    if m:
        ajuste_pct = float(next(g for g in m.groups() if g).replace(",", "."))
    m = _RE_AJUSTE_NEG.search(texto)
    if m:
        ajuste_pct = -float(m.group(1).replace(",", "."))

    preco_por_imagem = None
    m = _RE_PRECO_IMAGEM.search(texto)
    if m:
        preco_por_imagem = int(m.group(1).replace(".", ""))

    ambientes = None
    m = _RE_AMBIENTES.search(texto)
    if m:
        ambientes = int(m.group(1))

    estrategia = "auto"
    if _RE_ESTRATEGIA_PLAN.search(texto):
        estrategia = "planilha"
    elif _RE_ESTRATEGIA_HIST.search(texto):
        estrategia = "historico"

    blocos = _split_secoes(texto, categorias)
    listas = {cat: _extrai_lista(blocos.get(cat, "")) for cat in categorias}

    if texto.strip() and not any(listas.values()):
        avisos.append("Não consegui identificar nenhuma seção (Externas/Internas/Plantas). "
                      "Use cabeçalhos tipo 'Externas:' seguidos de uma lista.")

    return {
        "cliente": {
            "empresa": cliente or "CLIENTE",
            "ref": ref or "PROJETO",
            "contato": contato or "—",
        },
        **listas,
        "desconto_pct": desconto_pct,
        "desconto_label": None,
        "ajuste_planilha_pct": ajuste_pct,
        "preco_por_imagem": preco_por_imagem,
        "ambientes": ambientes,
        "estrategia": estrategia,
        "mostrar_precos_individuais": bool(_RE_PRECOS_IND.search(texto)),
        "_origem": "local",
        "_avisos": avisos,
    }


def _system_prompt(categorias: list[str] | tuple[str, ...]) -> str:
    linhas_schema = ",\n".join(f'  "{cat}": ["nome do item", ...]' for cat in categorias)
    categorias_txt = ", ".join(categorias)
    return f"""Você é um assistente que converte descrições livres em português de
propostas comerciais da Flying Studio em JSON estruturado. Devolva APENAS JSON válido,
sem markdown, sem texto extra.

Schema:
{{
  "cliente": {{"empresa": "...", "ref": "...", "contato": "..."}},
{linhas_schema},
  "desconto_pct": 0,
  "desconto_label": null,
  "ajuste_planilha_pct": 0,
  "preco_por_imagem": null,
  "estrategia": "auto" | "planilha" | "historico",
  "mostrar_precos_individuais": false
}}

Categorias ativas do catálogo: {categorias_txt}. Use SOMENTE essas chaves de
categoria (além de cliente/desconto/estrategia) — não invente outras.

Regras importantes:
- Se o usuário mencionou explicitamente "preço de planilha" ou "tabela padrão",
  estrategia = "planilha".
- Se mencionou "histórico do cliente" ou "preço médio do cliente" ou "mesma base
  do projeto anterior", estrategia = "historico".
- Caso contrário estrategia = "auto".
- Para imagens, mantenha o nome curto do ambiente (ex.: "Fachada", "Lobby",
  "Implantação Térreo"). NÃO prefixe com "Perspectiva" — o gerador faz isso.
- Se o usuário disser "10% de desconto", desconto_pct = 10.
- "planilha + 10%", "10% em cima", "cliente novo" → ajuste_planilha_pct = 10;
  "planilha - 5%" → -5. É ajuste no preço dos itens, NÃO desconto.
- "2.400 por imagem", "média de 2.200 a imagem" → preco_por_imagem = 2400 (número).
- Item com valor dito pelo usuário ("institucional de 2:00 = 15.000") vai como
  {{"descricao": "Filme institucional de até 2:00", "preco": 15000}}. Sem valor
  dito, só a descrição (string). NUNCA invente o número.
- Se mencionar "preços individuais por imagem" ou "coluna de valor",
  mostrar_precos_individuais = true.
- NUNCA invente preços ou valores em reais.
"""


# Mantido para compatibilidade: prompt com as 3 categorias históricas.
SYSTEM_PROMPT = _system_prompt(CATEGORIAS_FALLBACK)


def _chamar_openai(texto: str, categorias: list[str] | tuple[str, ...] | None = None) -> dict[str, Any] | None:
    """Chamada crua ao modelo. Devolve None sem OPENAI_API_KEY; propaga exceções."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    categorias = list(categorias) if categorias is not None else list(CATEGORIAS_FALLBACK)
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    modelo = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=modelo,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": _system_prompt(categorias)},
            {"role": "user", "content": texto},
        ],
    )
    return json.loads(resp.choices[0].message.content or "{}")


def _preencher_defaults(data: dict[str, Any], categorias: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    categorias = list(categorias) if categorias is not None else list(CATEGORIAS_FALLBACK)
    data.setdefault("_avisos", [])
    data.setdefault("desconto_label", None)
    data.setdefault("mostrar_precos_individuais", False)
    data.setdefault("estrategia", "auto")
    cli = data.setdefault("cliente", {})
    cli.setdefault("empresa", "CLIENTE")
    cli.setdefault("ref", "PROJETO")
    cli.setdefault("contato", "—")
    for k in categorias:
        data.setdefault(k, [])
    data.setdefault("desconto_pct", 0)
    return data


def parse(texto: str, categorias: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Tenta OpenAI; em falta de chave ou falha, usa o parser local.

    `categorias` são as categorias ativas do catálogo (`TabelaPrecos.categorias()`);
    sem elas, cai no fallback histórico (externas/internas/plantas).
    """
    categorias = list(categorias) if categorias is not None else list(CATEGORIAS_FALLBACK)
    texto = (texto or "").strip()
    if not texto:
        return parse_local("", categorias)

    aviso_falha = None
    try:
        bruto = _chamar_openai(texto, categorias)
    except Exception as exc:  # noqa: BLE001 — qualquer falha da API cai no local
        bruto = None
        aviso_falha = f"OpenAI indisponível, usando parser local. ({exc})"

    if bruto is not None:
        data = _preencher_defaults(bruto, categorias)
        data["_origem"] = "openai"
        # Complementa lacunas com o parser local (o modelo às vezes omite seções).
        local = parse_local(texto, categorias)
        for k in categorias:
            if not data.get(k) and local.get(k):
                data[k] = local[k]
        return data

    out = parse_local(texto, categorias)
    if aviso_falha:
        out["_avisos"].insert(0, aviso_falha)
    return out
