# Automação de Proposta — Plano 3: docx + IA + API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar a proposta final em `.docx` timbrado, interpretar texto livre com OpenAI (fallback regex local), subir o arquivo no Cloudflare R2 e expor tudo numa API FastAPI autenticada — fechando o serviço backend completo.

**Architecture:** Quatro pacotes novos que compõem o que já existe: `app/docx/` (formatação BRL/extenso + gerador python-docx a partir da estrutura de `fechar_orcamento`), `app/ia/` (parser OpenAI com fallback regex, portado do legado), `app/storage/` (upload R2 via boto3, degradação graciosa), `app/servicos/` (orquestração: NEON→TabelaPrecos→orçamento→docx→R2→NEON) e `app/api/` (FastAPI + Bearer token). O domínio `app/dominio/` permanece puro e inalterado; a IA nunca produz número.

**Tech Stack:** Python 3.12+, FastAPI + uvicorn, python-docx, openai (gpt-4o-mini), boto3 (R2/S3), psycopg3, pytest + httpx.

## Roadmap dos planos (contexto)

Plano 3 de 4. (1) Núcleo determinístico ✅. (2) Persistência NEON + histórico ✅. **(3) docx + IA + API (este).** (4) UI no hub Next.js.

## Global Constraints

- Python **3.12+**. Código e comentários em **português**.
- **`app/dominio/` permanece puro e INALTERADO** — nenhum arquivo lá importa psycopg, rede, openai ou docx.
- **A IA nunca produz um número**: o LLM só devolve itens estruturados (nomes/listas); preço vem de `carregar_tabela_precos(conn)` (NEON) ou do histórico; soma/desconto são código do domínio.
- **NEON é a única fonte de preços em runtime**: todo caminho de produção que precifica usa `app.db.repo_precos.carregar_tabela_precos(conn)`. NUNCA chamar `TabelaPrecos()` sem argumento fora de teste (o default JSON do domínio não é fonte de produção).
- Modelo OpenAI: env `OPENAI_MODEL`, default **`gpt-4o-mini`**; chave em `OPENAI_API_KEY`. Sem chave/falha → fallback parser regex local (a API continua funcionando em "modo manual").
- R2: envs `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, opcional `R2_PUBLIC_BASE_URL`. Sem credenciais ou upload falhando → `docx_url=None` e o `.docx` continua disponível pelo endpoint de download direto.
- Auth da API: header `Authorization: Bearer <token>` comparado com env `API_TOKEN`. Sem `API_TOKEN` definido no ambiente → todas as rotas protegidas devolvem **503** (nunca abrir sem querer).
- Testes: sem rede em teste — OpenAI e R2 são sempre monkeypatched; testes de banco usam a marca `@pytest.mark.db` e o fixture `db` existente (pulam se o Postgres de teste estiver fora; `docker compose up -d db-test` a partir de `aut-proposta/`).
- Timbrado: `docs/superpowers/specs/TIMBRADO_FLYINGSTUDIO.docx` é copiado para `aut-proposta/app/docx/timbrado/TIMBRADO_FLYINGSTUDIO.docx` (versionado). Sem ele no runtime → documento sem timbrado com cabeçalho programático simples (não é erro).
- Dinheiro: formato BRL `R$3.660,00` (ponto de milhar, vírgula decimal) e valor por extenso em português — exatamente como o legado (`_brl`, `_extenso`).
- Categorias: `("externas", "internas", "plantas")`. Extras do legado (tour virtual, filmes, apps, drone) ficam FORA deste plano.
- `gerar_docx` consome a estrutura de `fechar_orcamento` (`{"orcamento": {...}, "financeiro": {...}}`) — dicts serializáveis, nunca os dataclasses do domínio.
- Rodar pytest sempre de dentro de `aut-proposta/`.

---

### Task 1: Formatação de valores (BRL, extenso, data)

**Files:**
- Modify: `aut-proposta/pyproject.toml` (novas dependências)
- Create: `aut-proposta/app/docx/__init__.py`
- Create: `aut-proposta/app/docx/formatos.py`
- Test: `aut-proposta/tests/docx/__init__.py`, `aut-proposta/tests/docx/test_formatos.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `app.docx.formatos.brl(valor: float) -> str` — `3660.0 → "R$3.660,00"`.
  - `app.docx.formatos.extenso(valor: float) -> str` — `33660 → "Trinta e Três Mil, Seiscentos e Sessenta Reais"`.
  - `app.docx.formatos.data_extenso(data: datetime.date) -> str` — `date(2026,7,19) → "19 de Julho de 2026"`.

- [ ] **Step 1: Adicionar dependências ao `pyproject.toml`**

Em `aut-proposta/pyproject.toml`, substituir as seções `dependencies` e `dev`:

```toml
dependencies = [
    "psycopg[binary]>=3.2",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "python-docx>=1.1",
    "openai>=1.40",
    "boto3>=1.34",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
```

Instalar: a partir de `aut-proposta/`, `pip install -e ".[dev]"`.

- [ ] **Step 2: Escrever os testes (falha primeiro)**

`aut-proposta/tests/docx/__init__.py` vazio. `aut-proposta/tests/docx/test_formatos.py`:

```python
import datetime as dt

from app.docx.formatos import brl, data_extenso, extenso


def test_brl_milhares():
    assert brl(3660.0) == "R$3.660,00"
    assert brl(33660.0) == "R$33.660,00"
    assert brl(1234567.89) == "R$1.234.567,89"


def test_brl_pequeno():
    assert brl(0) == "R$0,00"
    assert brl(950) == "R$950,00"


def test_extenso_casos_reais():
    # Caso GALLI do Plano 1: total 33660.
    assert extenso(33660) == "Trinta e Três Mil, Seiscentos e Sessenta Reais"
    assert extenso(1) == "Um Real"
    assert extenso(0) == "Zero Reais"
    assert extenso(100) == "Cem Reais"
    assert extenso(1000) == "Mil Reais"
    assert extenso(2_000_000) == "Dois Milhões Reais"


def test_data_extenso():
    assert data_extenso(dt.date(2026, 7, 19)) == "19 de Julho de 2026"
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/docx/test_formatos.py -v`
Expected: FAIL (ModuleNotFoundError: app.docx.formatos).

- [ ] **Step 4: Implementar `formatos.py`**

`aut-proposta/app/docx/__init__.py` vazio. `aut-proposta/app/docx/formatos.py` (porte fiel de `_brl`/`_extenso`/`_data_extenso` do legado `docx_writer.py`):

```python
"""Formatação de valores monetários, extenso e datas em português."""
from __future__ import annotations

import datetime as dt

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_UNIDADES = ["", "Um", "Dois", "Três", "Quatro", "Cinco", "Seis", "Sete", "Oito", "Nove",
             "Dez", "Onze", "Doze", "Treze", "Quatorze", "Quinze", "Dezesseis", "Dezessete",
             "Dezoito", "Dezenove"]
_DEZENAS = ["", "", "Vinte", "Trinta", "Quarenta", "Cinquenta", "Sessenta", "Setenta",
            "Oitenta", "Noventa"]
_CENTENAS = ["", "Cento", "Duzentos", "Trezentos", "Quatrocentos", "Quinhentos",
             "Seiscentos", "Setecentos", "Oitocentos", "Novecentos"]


def brl(valor: float) -> str:
    s = f"{valor:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R${s}"


def data_extenso(data: dt.date) -> str:
    return f"{data.day:02d} de {MESES_PT[data.month - 1]} de {data.year}"


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "Cem"
    partes: list[str] = []
    c, r = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if r < 20:
        if r:
            partes.append(_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        if u:
            partes.append(f"{_DEZENAS[d]} e {_UNIDADES[u]}")
        else:
            partes.append(_DEZENAS[d])
    return " e ".join(partes)


def extenso(valor: float) -> str:
    inteiro = int(round(valor))
    if inteiro == 0:
        return "Zero Reais"

    milhoes, resto = divmod(inteiro, 1_000_000)
    milhares, unidades = divmod(resto, 1_000)

    blocos: list[str] = []
    if milhoes:
        blocos.append(f"{_ate_999(milhoes)} {'Milhão' if milhoes == 1 else 'Milhões'}")
    if milhares:
        blocos.append("Mil" if milhares == 1 else f"{_ate_999(milhares)} Mil")
    if unidades:
        blocos.append(_ate_999(unidades))

    texto = ", ".join(blocos) if len(blocos) > 1 else blocos[0]
    return f"{texto} {'Real' if inteiro == 1 else 'Reais'}"
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/docx/test_formatos.py -v`
Expected: PASS (4 passed). Rode `pytest` completo: os 41 do Planos 1-2 continuam passando.

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/pyproject.toml aut-proposta/app/docx/ aut-proposta/tests/docx/
git commit -m "feat(proposta): formatação BRL, extenso e data (base do docx)"
```

---

### Task 2: Gerador do .docx timbrado

**Files:**
- Copy: `docs/superpowers/specs/TIMBRADO_FLYINGSTUDIO.docx` → `aut-proposta/app/docx/timbrado/TIMBRADO_FLYINGSTUDIO.docx`
- Create: `aut-proposta/app/docx/gerador.py`
- Test: `aut-proposta/tests/docx/test_gerador.py`

**Interfaces:**
- Consumes: `app.docx.formatos.{brl, extenso, data_extenso}`; a estrutura `fechado` devolvida por `app.dominio.orcamento.fechar_orcamento` (`{"orcamento": {"subtotal", "total_imagens", "externas": {"nome","qtd","total","itens":[{"descricao","preco","fonte"}]}, "internas": {...}, "plantas": {...}}, "financeiro": {"subtotal","desconto_pct","desconto_valor","total","rotulo"}}`).
- Produces: `app.docx.gerador.gerar_docx(cliente: dict[str, str], fechado: dict, saida: Path, data: datetime.date | None = None, mostra_precos_individuais: bool = False) -> Path` — `cliente` tem chaves `empresa`, `ref`, `contato`. Gera o documento completo (capa, apresentação, tabelas de itens, totais, pagamento, prazos, materiais, considerações, entrega, assinatura) sobre o timbrado se existir, e devolve `saida`.

**Nota:** o porte vem de `Aut_proposta_old/Flying-studio-proposta/flying/docx_writer.py`. Diferenças intencionais: (a) consome o dict `fechado` (não o dataclass `Orcamento` — o legado guardava `desconto_pct` dentro do orçamento; aqui o desconto vem de `fechado["financeiro"]`); (b) sem seção de extras (fora de escopo); (c) sem conversão `.doc` via LibreOffice — só `.docx`; (d) sem logo PNG — fallback sem timbrado usa cabeçalho de texto.

- [ ] **Step 1: Copiar o timbrado versionado**

```bash
mkdir -p aut-proposta/app/docx/timbrado
cp docs/superpowers/specs/TIMBRADO_FLYINGSTUDIO.docx aut-proposta/app/docx/timbrado/
```

- [ ] **Step 2: Escrever os testes (falha primeiro)**

`aut-proposta/tests/docx/test_gerador.py`:

```python
"""Valida o .docx gerado reabrindo com python-docx e inspecionando o texto."""
import datetime as dt

import pytest
from docx import Document

from app.docx.gerador import gerar_docx

CLIENTE = {"empresa": "GALLI", "ref": "Empreendimento Teste", "contato": "Daniel Pucci"}


def _fechado_galli():
    # Espelho reduzido do caso real GALLI (Plano 1): subtotal 38250, 12% -> 33660.
    return {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 38250, "total_imagens": 3,
            "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                         "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000,
                                    "fonte": "planilha:fachada"}]},
            "internas": {"nome": "internas", "qtd": 1, "total": 1750,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1750,
                                    "fonte": "planilha:interna_diversa"}]},
            "plantas": {"nome": "plantas", "qtd": 1, "total": 33500,
                        "itens": [{"descricao": "Planta Humanizada Tipo", "preco": 33500,
                                   "fonte": "planilha:planta_tipo"}]},
        },
        "financeiro": {"subtotal": 38250, "desconto_pct": 12.0, "desconto_valor": 4590.0,
                       "total": 33660.0, "rotulo": "12% parceria"},
    }


def _texto_completo(path):
    doc = Document(str(path))
    partes = [p.text for p in doc.paragraphs]
    for tab in doc.tables:
        for row in tab.rows:
            for cell in row.cells:
                partes.append(cell.text)
    return "\n".join(partes)


def test_gera_docx_com_conteudo_essencial(tmp_path):
    saida = tmp_path / "proposta.docx"
    resultado = gerar_docx(CLIENTE, _fechado_galli(), saida, data=dt.date(2026, 7, 19))

    assert resultado == saida
    assert saida.exists()
    texto = _texto_completo(saida)

    assert "PROPOSTA COMERCIAL" in texto
    assert "GALLI" in texto
    assert "EMPREENDIMENTO TESTE" in texto
    assert "DANIEL PUCCI" in texto
    assert "R$33.660,00" in texto            # investimento final
    assert "R$38.250,00" in texto            # valor bruto
    assert "12% parceria" in texto           # rótulo do desconto
    assert "Trinta e Três Mil, Seiscentos e Sessenta Reais" in texto
    assert "Perspectiva Fachada" in texto
    assert "Planta Humanizada Tipo" in texto
    assert "19 de Julho de 2026" in texto
    # Seções fixas
    for secao in ("APRESENTAÇÃO", "FORMA DE PAGAMENTO", "PRAZOS DE ENTREGA",
                  "CONSIDERAÇÕES", "ENTREGA FINAL"):
        assert secao in texto


def test_sem_desconto_nao_mostra_valor_bruto(tmp_path):
    fechado = _fechado_galli()
    fechado["financeiro"] = {"subtotal": 38250, "desconto_pct": 0.0,
                             "desconto_valor": 0.0, "total": 38250.0, "rotulo": ""}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "VALOR BRUTO" not in texto
    assert "R$38.250,00" in texto


def test_categoria_vazia_omitida(tmp_path):
    fechado = _fechado_galli()
    fechado["orcamento"]["plantas"] = {"nome": "plantas", "qtd": 0, "total": 0, "itens": []}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "PLANTAS HUMANIZADAS" not in texto


def test_precos_individuais_opcionais(tmp_path):
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, _fechado_galli(), saida, mostra_precos_individuais=True)
    texto = _texto_completo(saida)
    assert "R$3.000,00" in texto  # preço do item aparece na tabela
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/docx/test_gerador.py -v`
Expected: FAIL (ModuleNotFoundError: app.docx.gerador).

- [ ] **Step 4: Implementar `gerador.py`**

`aut-proposta/app/docx/gerador.py`:

```python
"""Gera o .docx da proposta no padrão visual Flying Studio.

Porte de flying/docx_writer.py do sistema antigo, adaptado para consumir a
estrutura de fechar_orcamento ({"orcamento": ..., "financeiro": ...}).
Usa o papel timbrado versionado em app/docx/timbrado/ quando existir.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.docx.formatos import brl, data_extenso, extenso

TIMBRADO_PATH = Path(__file__).resolve().parent / "timbrado" / "TIMBRADO_FLYINGSTUDIO.docx"

COR_PRIMARIA = RGBColor(0x7C, 0x5C, 0xFF)
COR_PRIMARIA_DARK = RGBColor(0x5B, 0x3C, 0xFF)
COR_ACENTO = RGBColor(0x9D, 0xDB, 0x1A)
COR_TEXTO = RGBColor(0x1F, 0x23, 0x30)
COR_TEXTO_SOFT = RGBColor(0x5C, 0x64, 0x73)
COR_BRANCO = RGBColor(0xFF, 0xFF, 0xFF)

HEX_PRIMARIA = "7C5CFF"
HEX_PRIMARIA_DARK = "5B3CFF"
HEX_OFFWHITE = "F7F8FB"

FONTE = "Calibri"

ROTULOS_CATEGORIA = {
    "externas": "ILUSTRAÇÕES EXTERNAS",
    "internas": "ILUSTRAÇÕES INTERNAS",
    "plantas": "PLANTAS HUMANIZADAS",
}


# ---------- helpers de baixo nível ----------


def _shade_cell(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _set_cell_borders(cell, *, bottom_color="E7E9EE", bottom_size=4):
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcBorders"))
    if existing is not None:
        tc_pr.remove(existing)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "right"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "nil")
        borders.append(b)
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), str(bottom_size))
    bot.set(qn("w:color"), bottom_color)
    borders.append(bot)
    tc_pr.append(borders)


def _set_cell_no_borders(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcBorders"))
    if existing is not None:
        tc_pr.remove(existing)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "right", "bottom"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "nil")
        borders.append(b)
    tc_pr.append(borders)


def _run(p, texto, *, bold=False, italic=False, size=11, color=COR_TEXTO):
    r = p.add_run(texto)
    r.font.name = FONTE
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color:
        r.font.color.rgb = color
    return r


def _add_par(doc, texto="", *, bold=False, italic=False, size=11, color=COR_TEXTO,
             alignment=None, space_after=4, space_before=0):
    p = doc.add_paragraph()
    if alignment is not None:
        p.alignment = alignment
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.line_spacing = 1.25
    if texto:
        _run(p, texto, bold=bold, italic=italic, size=size, color=color)
    return p


def _add_titulo_secao(doc, numero, titulo):
    p1 = doc.add_paragraph()
    p1.paragraph_format.space_after = Pt(0)
    p1.paragraph_format.space_before = Pt(8)
    _run(p1, f"{numero}.", bold=True, size=9, color=COR_PRIMARIA)

    p2 = doc.add_paragraph()
    p2.paragraph_format.space_after = Pt(10)
    _run(p2, titulo.upper(), bold=True, size=18, color=COR_TEXTO)
    return p2


def _add_bullet(doc, texto, *, label=None):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.7)
    p.paragraph_format.first_line_indent = Cm(-0.5)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.3
    _run(p, "•  ", bold=True, color=COR_PRIMARIA, size=11)
    if label:
        _run(p, f"{label}: ", bold=True, color=COR_TEXTO, size=11)
    _run(p, texto, color=COR_TEXTO, size=11)
    return p


def _quebra_pagina(doc):
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def _limpar_corpo(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


# ---------- componentes ----------


def _caixa_capa(doc, *, cliente, qtd_img, valor_bruto, valor_final, desconto_pct, rotulo):
    linhas = [
        ("CLIENTE", cliente["empresa"].upper(), False),
        ("PROJETO", cliente["ref"].upper(), False),
        ("AOS CUIDADOS DE", cliente["contato"].upper(), False),
    ]
    if qtd_img:
        linhas.append(("IMAGENS", f"{qtd_img} unidades", False))
    if desconto_pct > 0:
        linhas.append(("VALOR BRUTO", brl(valor_bruto), False))
        linhas.append((f"DESCONTO ({rotulo or f'{desconto_pct}%'})",
                       "-" + brl(valor_bruto - valor_final), False))
    linhas.append(("INVESTIMENTO", brl(valor_final), True))

    tab = doc.add_table(rows=len(linhas), cols=2)
    tab.autofit = False
    tab.columns[0].width = Cm(6.0)
    tab.columns[1].width = Cm(10.0)

    for i, (rotulo_l, valor, destaque) in enumerate(linhas):
        c1, c2 = tab.rows[i].cells
        c1.width = Cm(6.0)
        c2.width = Cm(10.0)
        _shade_cell(c1, HEX_PRIMARIA)
        _shade_cell(c2, HEX_PRIMARIA_DARK if destaque else HEX_PRIMARIA)
        _set_cell_no_borders(c1)
        _set_cell_no_borders(c2)
        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c2.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_before = Pt(6)
        p1.paragraph_format.space_after = Pt(6)
        _run(p1, rotulo_l, bold=True, size=9, color=COR_BRANCO)

        p2 = c2.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p2.paragraph_format.space_before = Pt(6)
        p2.paragraph_format.space_after = Pt(6)
        _run(p2, valor, bold=True, size=16 if destaque else 11,
             color=COR_ACENTO if destaque else COR_BRANCO)


def _tabela_categoria(doc, numero, bloco: dict[str, Any], *, mostra_precos):
    """bloco = {"qtd", "total", "itens": [{"descricao", "preco"}]}"""
    linhas_total = 1 + bloco["qtd"] + 1
    cols = 3 if mostra_precos else 2
    tab = doc.add_table(rows=linhas_total, cols=cols)
    tab.autofit = False
    if mostra_precos:
        tab.columns[0].width = Cm(2.0)
        tab.columns[1].width = Cm(10.5)
        tab.columns[2].width = Cm(3.5)
    else:
        tab.columns[0].width = Cm(2.5)
        tab.columns[1].width = Cm(13.5)

    cab = tab.rows[0]
    for c in cab.cells:
        _shade_cell(c, HEX_PRIMARIA)
        _set_cell_no_borders(c)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cab.cells[0].paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    _run(p, "ITEM", bold=True, size=9, color=COR_BRANCO)
    p = cab.cells[1].paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    _run(p, "DESCRIÇÃO DO SERVIÇO", bold=True, size=9, color=COR_BRANCO)
    if mostra_precos:
        p = cab.cells[2].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(4)
        _run(p, "VALOR", bold=True, size=9, color=COR_BRANCO)

    for idx, item in enumerate(bloco["itens"], start=1):
        row = tab.rows[idx]
        zebra = idx % 2 == 0
        for c in row.cells:
            if zebra:
                _shade_cell(c, HEX_OFFWHITE)
            _set_cell_borders(c, bottom_color="E7E9EE", bottom_size=4)
            c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p1 = row.cells[0].paragraphs[0]
        p1.paragraph_format.space_before = Pt(3)
        p1.paragraph_format.space_after = Pt(3)
        _run(p1, f"{numero}.{idx}", bold=True, size=10, color=COR_PRIMARIA_DARK)

        p2 = row.cells[1].paragraphs[0]
        p2.paragraph_format.space_before = Pt(3)
        p2.paragraph_format.space_after = Pt(3)
        _run(p2, item["descricao"], size=11, color=COR_TEXTO)

        if mostra_precos:
            p3 = row.cells[2].paragraphs[0]
            p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p3.paragraph_format.space_before = Pt(3)
            p3.paragraph_format.space_after = Pt(3)
            _run(p3, brl(item["preco"]), bold=True, size=11, color=COR_TEXTO)

    rod = tab.rows[-1]
    for c in rod.cells:
        _shade_cell(c, HEX_PRIMARIA_DARK)
        _set_cell_no_borders(c)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p1 = rod.cells[0].paragraphs[0]
    p1.paragraph_format.space_before = Pt(4)
    p1.paragraph_format.space_after = Pt(4)
    _run(p1, str(bloco["qtd"]), bold=True, size=11, color=COR_BRANCO)
    if mostra_precos:
        p2 = rod.cells[1].paragraphs[0]
        p2.paragraph_format.space_before = Pt(4)
        p2.paragraph_format.space_after = Pt(4)
        _run(p2, "Subtotal", bold=True, size=11, color=COR_BRANCO)
        p3 = rod.cells[2].paragraphs[0]
        p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p3.paragraph_format.space_before = Pt(4)
        p3.paragraph_format.space_after = Pt(4)
        _run(p3, brl(bloco["total"]), bold=True, size=11, color=COR_BRANCO)
    else:
        p2 = rod.cells[1].paragraphs[0]
        p2.paragraph_format.space_before = Pt(4)
        p2.paragraph_format.space_after = Pt(4)
        _run(p2, f"Subtotal     {brl(bloco['total'])}", bold=True, size=11, color=COR_BRANCO)


# ---------- documento principal ----------


def gerar_docx(
    cliente: dict[str, str],
    fechado: dict[str, Any],
    saida: Path,
    data: dt.date | None = None,
    mostra_precos_individuais: bool = False,
) -> Path:
    data = data or dt.date.today()
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]

    if TIMBRADO_PATH.exists():
        doc = Document(str(TIMBRADO_PATH))
        _limpar_corpo(doc)
    else:
        doc = Document()
        secao = doc.sections[0]
        secao.left_margin = Cm(2.5)
        secao.right_margin = Cm(2.5)
        secao.top_margin = Cm(3.0)
        secao.bottom_margin = Cm(2.3)
        header = secao.header
        p = header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(p, "FLYING studio", bold=True, size=14, color=COR_PRIMARIA)

    valor_bruto = fin["subtotal"]
    valor_final = fin["total"]

    # ===== CAPA =====
    _add_par(doc, "PROPOSTA COMERCIAL", bold=True, size=28, color=COR_PRIMARIA,
             space_before=18, space_after=2)
    _add_par(doc, "Imagens, Filmes e Tecnologias 3D", size=13, color=COR_TEXTO_SOFT,
             space_after=12)
    _add_par(doc, data_extenso(data).upper(), size=9, color=COR_TEXTO_SOFT, space_after=24)

    _caixa_capa(
        doc,
        cliente=cliente,
        qtd_img=orc["total_imagens"],
        valor_bruto=valor_bruto,
        valor_final=valor_final,
        desconto_pct=fin["desconto_pct"],
        rotulo=fin["rotulo"],
    )
    _add_par(doc, "", space_after=4)
    _add_par(doc, f"Por extenso: {extenso(valor_final)}.", italic=True, size=9,
             color=COR_TEXTO_SOFT, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_after=24)

    _quebra_pagina(doc)

    # ===== 01 APRESENTAÇÃO =====
    _add_titulo_secao(doc, "01", "Apresentação")
    _add_par(doc,
             "A Flying Studio presta serviços de computação gráfica e tecnologias que se aplicam aos "
             "lançamentos imobiliários e remanescentes. Em nosso atendimento diário, desenvolvemos laços "
             "com projeto e auxiliamos em layout, estudos de projetos e fachadas, de decoração e "
             "paisagismo de acordo com cada necessidade.",
             color=COR_TEXTO_SOFT, space_after=6)
    _add_par(doc, "Para projetos de arquitetura, decoração e paisagismo, consulte a NID STUDIO.",
             italic=True, color=COR_TEXTO_SOFT, space_after=18)

    # ===== 02 ITENS =====
    _add_titulo_secao(doc, "02", "Itens a Serem Desenvolvidos")

    secao_num = 0
    for cat in ("externas", "internas", "plantas"):
        bloco = orc[cat]
        if not bloco["qtd"]:
            continue
        secao_num += 1
        _add_par(doc, ROTULOS_CATEGORIA[cat], bold=True, size=11, color=COR_PRIMARIA_DARK,
                 space_before=8, space_after=4)
        _tabela_categoria(doc, f"2.{secao_num}", bloco,
                          mostra_precos=mostra_precos_individuais)
        _add_par(doc, "", space_after=8)

    # Totais inline
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    if orc["total_imagens"]:
        _run(p, "Imagens: ", color=COR_TEXTO_SOFT)
        _run(p, str(orc["total_imagens"]), bold=True)
    _run(p, "    ·    Valor bruto: ", color=COR_TEXTO_SOFT)
    _run(p, brl(valor_bruto), bold=True)

    if fin["desconto_pct"] > 0:
        rotulo = fin["rotulo"] or f"{fin['desconto_pct']}% de Desconto"
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        _run(p, "Desconto aplicado: ", color=COR_TEXTO_SOFT)
        _run(p, rotulo, bold=True)
        _run(p, "    ·    Valor do desconto: ", color=COR_TEXTO_SOFT)
        _run(p, "-" + brl(fin["desconto_valor"]), bold=True, color=COR_PRIMARIA_DARK)

    _add_par(doc, "", space_after=4)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    _run(p, "INVESTIMENTO TOTAL  ", bold=True, size=14, color=COR_PRIMARIA)
    _run(p, brl(valor_final), bold=True, size=20, color=COR_PRIMARIA_DARK)
    _add_par(doc, f"({extenso(valor_final)})", italic=True, color=COR_TEXTO_SOFT,
             space_after=18)

    _quebra_pagina(doc)

    # ===== 03 FORMA DE PAGAMENTO =====
    _add_titulo_secao(doc, "03", "Forma de Pagamento")
    for pct, marco in ((50, "Na aprovação desta Proposta"),
                       (25, "Envio dos Shades"),
                       (25, "Envio HR — Imagens finais")):
        v = valor_final * (pct / 100.0)
        _add_bullet(doc, marco, label=f"{pct}%  ({brl(v)})")
    _add_par(doc, "", space_after=12)

    # ===== 04 PRAZOS =====
    _add_titulo_secao(doc, "04", "Prazos de Entrega")
    _add_bullet(doc, "20 (Vinte) dias", label="Shades")
    _add_bullet(doc, "15 (Quinze) dias após a aprovação dos Shades", label="1º Tiro de Apresentação")
    _add_bullet(doc, "10 (Dez) dias para contemplar e enviar novos tiros", label="Revisões")
    _add_par(doc,
             "Os prazos passam a contar após o recebimento de todos os projetos, informações e aprovações "
             "de etapas para o desenvolvimento de cada item. Não iniciamos os trabalhos sem o DWG e as "
             "aprovações necessárias desta proposta.",
             italic=True, size=9, color=COR_TEXTO_SOFT, space_before=6, space_after=18)

    _quebra_pagina(doc)

    # ===== 05 MATERIAIS NECESSÁRIOS =====
    _add_titulo_secao(doc, "05", "Materiais Necessários")
    _add_bullet(doc, "Plantas · Elevação da Fachada · Estudo de Cores da Fachada · Cortes.",
                label="Arquitetura")
    _add_bullet(doc, "Implantação · Detalhamentos · Especificação de Revestimentos · Estudo de "
                     "Vegetação com Especificação de Espécies · Referências do Mobiliário.",
                label="Paisagismo")
    _add_bullet(doc, "Plantas com Layout · Desenhos de Pisos · Elevações de Paredes · Especificações "
                     "de Materiais · Projeto de Forro e Iluminação · Descrição ou book de mobiliários.",
                label="Decoração")
    _add_par(doc, "", space_after=12)

    # ===== 06 CONSIDERAÇÕES =====
    _add_titulo_secao(doc, "06", "Considerações")
    consideracoes = [
        ("Etapas e Tiros de Aprovação", "Esta proposta contempla o envio inicial do tiro de Shade, seguido do tiro de apresentação denominado “R00”. Estão inclusas no escopo 03 (três) rodadas de revisões, denominadas “R01”, “R02” e “R03”, culminando na entrega final denominada “HR” (High Resolution)."),
        ("Ajustes Finos e Adicionais", "A partir do tiro “R00”, as rodadas seguintes consistem exclusivamente em ajustes finos. A partir de um eventual quarto tiro de apresentação (“R04”), será cobrado um adicional de 25% do valor da imagem por tiro extra solicitado, bem como quaisquer tiros adicionais solicitados após a entrega do HR."),
        ("Plataforma Oficial de Revisão", "Para garantir a organização, a agilidade e a precisão técnica das refações, todo o processo de feedback, comentários e aprovações (filmes e imagens 3D) será realizado exclusivamente através do software Frame.io/Adobe."),
        ("Mecânica de Apontamentos", "A Contratada fornecerá à Contratante um link de acesso seguro à plataforma. Pelo Frame.io/Adobe, o cliente poderá inserir comentários, desenhar marcações, anexar informações (pdf, foto, dwg, etc.) e solicitar ajustes exatamente no frame do vídeo ou no ponto específico da imagem estática que deseja alterar."),
        ("Alterações de Projeto", "Quaisquer alterações nos projetos originais (sejam de design de interiores, arquitetônico ou paisagismo) fornecidos inicialmente implicam em cobranças extras de modelagem, que serão orçadas e aprovadas em comum acordo."),
        ("Refação e Remodelagem", "Havendo mudanças significativas no projeto que resultem na perda de até 50% da imagem já construída, o trabalho será considerado e cobrado como uma imagem nova."),
        ("Paralisação do Projeto", "Em caso de paralisação total ou parcial do escopo por um período de até 60 (sessenta) dias, deverá ser feito o acerto financeiro imediato das etapas já executadas. Considera-se que cada tiro enviado após a aprovação do R00 corresponde a 25% do valor total da imagem."),
        ("Cancelamento", "Em caso de descontinuidade e cancelamento do produto ou lançamento por qualquer motivo por parte da Contratante, considera-se justa e devida a quitação integral do saldo previsto nesta proposta."),
        ("Direitos de Uso", "A Contratada cede à Contratante os direitos de uso das imagens produzidas para uso promocional em todo o seu material publicitário, única e exclusivamente vinculadas ao empreendimento contratado, não havendo débitos/atrasos financeiros."),
    ]
    for titulo, texto in consideracoes:
        _add_bullet(doc, texto, label=titulo)
    _add_par(doc, "", space_after=12)

    # ===== 07 ENTREGA FINAL =====
    _add_titulo_secao(doc, "07", "Entrega Final")
    entregas = [
        ("Formato e Envio", "Todo o material finalizado será enviado digitalmente via servidor FTP, link seguro para download ou cadastrados no Frame.io/Adobe."),
        ("Resolução das Imagens Estáticas", "As imagens finais (“HR”) serão entregues com 6000px no lado maior a 300dpi. Após a entrega do HR, o projeto é considerado concluído. Caso surja a necessidade de novas configurações nessa etapa, ficamos à disposição para avaliar e orçar como um novo serviço."),
        ("Impressão de até 1m", "Caso a Contratante necessite de imagens configuradas para impressões de até 1 (um) metro, a solicitação deve ser feita com antecedência à renderização final, sem custo adicional."),
        ("Impressão acima de 1m", "Para outdoors ou grandes painéis (acima de 1m), favor consultar previamente os valores adicionais de render — custo estimado de 20% do valor da imagem."),
        ("Animações / Filmes", "Os passeios virtuais e filmes integrados serão entregues em Full HD a 30 FPS, ou propostas via RINNO FILMS, consultar."),
    ]
    for titulo, texto in entregas:
        _add_bullet(doc, texto, label=titulo)
    _add_par(doc, "", space_after=18)

    # ===== ASSINATURA =====
    _add_par(doc, f"São Paulo, {data_extenso(data)}.", color=COR_TEXTO_SOFT, space_after=18)
    _add_par(doc, "De acordo,", space_after=24)
    _add_par(doc, "____________________________________________________",
             color=COR_TEXTO_SOFT, space_after=2)
    _add_par(doc, cliente["empresa"].upper(), bold=True, size=12, color=COR_PRIMARIA,
             space_after=2)
    _add_par(doc, f"A/C: {cliente['contato']}", color=COR_TEXTO_SOFT, size=9)

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/docx/test_gerador.py -v`
Expected: PASS (4 passed).

Nota para o teste `test_gera_docx_com_conteudo_essencial`: os títulos de seção são escritos com `titulo.upper()`, então "Apresentação" vira "APRESENTAÇÃO" — se falhar por acento, confira que o assert usa a forma acentuada maiúscula.

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/app/docx/ aut-proposta/tests/docx/
git commit -m "feat(proposta): gerador do .docx timbrado (porte do docx_writer)"
```

---

### Task 3: Parser de texto livre (OpenAI + fallback regex)

**Files:**
- Create: `aut-proposta/app/ia/__init__.py`
- Create: `aut-proposta/app/ia/parser.py`
- Test: `aut-proposta/tests/ia/__init__.py`, `aut-proposta/tests/ia/test_parser.py`

**Interfaces:**
- Consumes: env `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`).
- Produces:
  - `app.ia.parser.parse(texto: str) -> dict` — sempre devolve dict com as chaves: `cliente` (`{"empresa","ref","contato"}`), `externas`/`internas`/`plantas` (listas de str), `desconto_pct` (float), `desconto_label` (str|None), `estrategia` (`"auto"|"planilha"|"historico"`), `mostrar_precos_individuais` (bool), `_origem` (`"openai"|"local"`), `_avisos` (list[str]).
  - `app.ia.parser.parse_local(texto: str) -> dict` — parser regex puro (mesmo shape, `_origem="local"`).
  - `app.ia.parser._chamar_openai(texto: str) -> dict | None` — isolado para monkeypatch em teste; devolve o dict cru do modelo ou levanta exceção em falha.

**Nota:** porte de `flying/ai_parser.py`, reduzido às 3 categorias (sem tour/filmes/apps/drone/extras — fora de escopo) e sem leitura de JSON de preços (a IA não vê preço nenhum).

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/ia/__init__.py` vazio. `aut-proposta/tests/ia/test_parser.py`:

```python
import pytest

from app.ia import parser


TEXTO_EXEMPLO = """Cliente: GALLI, ref Residencial Aurora, a/c Daniel Pucci
Externas: Fachada vista da calçada, Jardim
Internas: Academia; Lobby
Plantas:
- Implantação Térreo
- Apartamento Tipo
10% de desconto, preço de planilha"""


def test_parse_local_extrai_tudo():
    out = parser.parse_local(TEXTO_EXEMPLO)
    assert out["cliente"]["empresa"] == "GALLI"
    assert out["cliente"]["ref"] == "Residencial Aurora"
    assert out["cliente"]["contato"] == "Daniel Pucci"
    assert out["externas"] == ["Fachada vista da calçada", "Jardim"]
    assert out["internas"] == ["Academia", "Lobby"]
    assert out["plantas"] == ["Implantação Térreo", "Apartamento Tipo"]
    assert out["desconto_pct"] == 10.0
    assert out["estrategia"] == "planilha"
    assert out["_origem"] == "local"


def test_parse_local_estrategia_historico():
    out = parser.parse_local("cliente BRNPAR, mesma base do projeto anterior. Internas: Academia")
    assert out["estrategia"] == "historico"


def test_parse_local_cliente_caps_sem_marcador():
    out = parser.parse_local("GALLI Residencial Aurora\nExternas: Fachada")
    assert out["cliente"]["empresa"] == "GALLI"
    assert any("assumi" in a for a in out["_avisos"])


def test_parse_local_vazio_avisa():
    out = parser.parse_local("")
    assert out["cliente"]["empresa"] == "CLIENTE"
    assert out["_avisos"]


def test_parse_usa_openai_quando_disponivel(monkeypatch):
    monkeypatch.setattr(parser, "_chamar_openai", lambda texto: {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada"], "internas": [], "plantas": [],
        "desconto_pct": 10, "estrategia": "planilha",
    })
    out = parser.parse("qualquer texto")
    assert out["_origem"] == "openai"
    assert out["cliente"]["empresa"] == "GALLI"
    # Defaults preenchidos mesmo quando o modelo omite chaves.
    assert out["mostrar_precos_individuais"] is False
    assert out["desconto_label"] is None


def test_parse_cai_para_local_quando_openai_falha(monkeypatch):
    def _explode(texto):
        raise RuntimeError("api fora")
    monkeypatch.setattr(parser, "_chamar_openai", _explode)
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "local"
    assert out["cliente"]["empresa"] == "GALLI"
    assert any("OpenAI indisponível" in a for a in out["_avisos"])


def test_parse_openai_complementado_pelo_local(monkeypatch):
    # Modelo devolveu só externas; local completa internas/plantas.
    monkeypatch.setattr(parser, "_chamar_openai", lambda texto: {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "—"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
    })
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "openai"
    assert out["internas"] == ["Academia", "Lobby"]


def test_parse_sem_chave_usa_local(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "local"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/ia/test_parser.py -v`
Expected: FAIL (ModuleNotFoundError: app.ia).

- [ ] **Step 3: Implementar `parser.py`**

`aut-proposta/app/ia/__init__.py` vazio. `aut-proposta/app/ia/parser.py`:

```python
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
    s = re.sub(r"^[\-\*•–—\d\.\)]+\s*", "", s)
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
        return [_limpa_item(l) for l in linhas if _limpa_item(l)]
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/ia/test_parser.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/ia/ aut-proposta/tests/ia/
git commit -m "feat(proposta): parser de texto livre (OpenAI + fallback regex)"
```

---

### Task 4: Storage R2 (upload do .docx)

**Files:**
- Create: `aut-proposta/app/storage/__init__.py`
- Create: `aut-proposta/app/storage/r2.py`
- Test: `aut-proposta/tests/storage/__init__.py`, `aut-proposta/tests/storage/test_r2.py`

**Interfaces:**
- Consumes: envs `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL` (opcional).
- Produces:
  - `app.storage.r2.r2_configurado() -> bool` — True se as 4 envs obrigatórias existem.
  - `app.storage.r2.enviar_docx(caminho: Path, chave: str) -> str | None` — sobe o arquivo para o bucket com `chave` (ex.: `propostas/proposta_12.docx`) e devolve a URL pública (`{R2_PUBLIC_BASE_URL}/{chave}` se definida, senão a URL S3 da conta). Sem credenciais ou em QUALQUER falha de upload, devolve `None` (nunca levanta — o chamador segue com download direto).
  - `app.storage.r2._cliente_s3()` — isolado para monkeypatch em teste.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/storage/__init__.py` vazio. `aut-proposta/tests/storage/test_r2.py`:

```python
import pytest

from app.storage import r2

ENVS = {
    "R2_ACCOUNT_ID": "conta123",
    "R2_ACCESS_KEY_ID": "chave",
    "R2_SECRET_ACCESS_KEY": "segredo",
    "R2_BUCKET": "propostas",
}


def _limpa_envs(monkeypatch):
    for k in list(ENVS) + ["R2_PUBLIC_BASE_URL"]:
        monkeypatch.delenv(k, raising=False)


def test_sem_credenciais_nao_configurado(monkeypatch):
    _limpa_envs(monkeypatch)
    assert r2.r2_configurado() is False


def test_sem_credenciais_enviar_devolve_none(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"conteudo")
    assert r2.enviar_docx(arq, "propostas/p.docx") is None


def test_upload_ok_devolve_url_publica(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://arquivos.flyingstudio.com.br")

    chamadas = {}

    class FakeS3:
        def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
            chamadas.update(Filename=Filename, Bucket=Bucket, Key=Key)

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())

    arq = tmp_path / "p.docx"
    arq.write_bytes(b"conteudo")
    url = r2.enviar_docx(arq, "propostas/proposta_1.docx")

    assert url == "https://arquivos.flyingstudio.com.br/propostas/proposta_1.docx"
    assert chamadas["Bucket"] == "propostas"
    assert chamadas["Key"] == "propostas/proposta_1.docx"


def test_upload_sem_base_url_usa_endpoint_r2(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)

    class FakeS3:
        def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
            pass

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    url = r2.enviar_docx(arq, "propostas/p.docx")
    assert url == "https://conta123.r2.cloudflarestorage.com/propostas/propostas/p.docx"


def test_falha_de_upload_devolve_none(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)

    class FakeS3:
        def upload_file(self, *a, **kw):
            raise RuntimeError("rede caiu")

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    assert r2.enviar_docx(arq, "propostas/p.docx") is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/storage/test_r2.py -v`
Expected: FAIL (ModuleNotFoundError: app.storage).

- [ ] **Step 3: Implementar `r2.py`**

`aut-proposta/app/storage/__init__.py` vazio. `aut-proposta/app/storage/r2.py`:

```python
"""Upload do .docx no Cloudflare R2 (API compatível com S3, via boto3).

Degradação graciosa: sem credenciais ou com upload falhando, devolve None e o
chamador segue oferecendo o download direto pela API (decisão do design, §7).
"""
from __future__ import annotations

import os
from pathlib import Path

_ENVS_OBRIGATORIAS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def r2_configurado() -> bool:
    return all(os.getenv(k) for k in _ENVS_OBRIGATORIAS)


def _cliente_s3():
    import boto3

    conta = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{conta}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def enviar_docx(caminho: Path, chave: str) -> str | None:
    """Sobe o arquivo e devolve a URL pública, ou None se não der (nunca levanta)."""
    if not r2_configurado():
        return None
    try:
        s3 = _cliente_s3()
        s3.upload_file(
            Filename=str(caminho),
            Bucket=os.environ["R2_BUCKET"],
            Key=chave,
            ExtraArgs={"ContentType": MIME_DOCX},
        )
    except Exception:  # noqa: BLE001 — falha de upload nunca derruba a geração
        return None

    base = os.getenv("R2_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{chave}"
    conta = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    return f"https://{conta}.r2.cloudflarestorage.com/{bucket}/{chave}"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/storage/test_r2.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/storage/ aut-proposta/tests/storage/
git commit -m "feat(proposta): storage R2 com degradação graciosa"
```

---

### Task 5: Serviço de proposta (orquestração)

**Files:**
- Create: `aut-proposta/app/servicos/__init__.py`
- Create: `aut-proposta/app/servicos/proposta.py`
- Modify: `aut-proposta/app/db/repo_propostas.py` (adicionar `atualizar_docx_url`)
- Test: `aut-proposta/tests/servicos/__init__.py`, `aut-proposta/tests/servicos/test_proposta.py`

**Interfaces:**
- Consumes: `app.db.repo_precos.carregar_tabela_precos(conn)`, `app.db.repo_propostas.{upsert_cliente, salvar_proposta}`, `app.historico.historico.Historico`, `app.historico.orcamento_historico.orcar_pelo_historico`, `app.dominio.orcamento.{orcar_pela_planilha, fechar_orcamento}`, `app.dominio.descontos.Desconto`, `app.docx.gerador.gerar_docx`, `app.storage.r2.enviar_docx`.
- Produces:
  - `app.db.repo_propostas.atualizar_docx_url(conn, proposta_id: int, docx_url: str) -> None` — `UPDATE propostas SET docx_url = %s WHERE id = %s`, dentro de `conn.transaction()`.
  - `app.servicos.proposta.levantar(conn, estrutura: dict) -> dict` — recebe a estrutura do parser (Task 3); resolve a estratégia (`"planilha"` → planilha; `"historico"` → histórico, com erro em `_avisos` + fallback planilha se o cliente não tem histórico; `"auto"` → histórico se `Historico(conn).tem_cliente(empresa)` senão planilha); monta `Desconto` percentual quando `desconto_pct > 0`; devolve `{"cliente": {...}, "fechado": fechar_orcamento(...), "estrategia_usada": str, "avisos": [...]}`. **Preços SEMPRE via `carregar_tabela_precos(conn)`.**
  - `app.servicos.proposta.gerar(conn, estrutura: dict, dir_saida: Path) -> dict` — chama `levantar`, grava cliente+proposta no NEON, gera o `.docx` em `dir_saida/proposta_<id>.docx`, tenta subir no R2 (`propostas/proposta_<id>.docx`), grava a URL quando sobe; devolve `{"proposta_id": int, "docx_path": str, "docx_url": str | None, "fechado": {...}, "avisos": [...]}`.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/servicos/__init__.py` vazio. `aut-proposta/tests/servicos/test_proposta.py`:

```python
from pathlib import Path

import pytest

from app.db.repo_propostas import salvar_proposta, upsert_cliente
from app.db.schema import aplicar_schema
from app.servicos import proposta as svc
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _estrutura(estrategia="planilha", empresa="GALLI", desconto=0.0):
    return {
        "cliente": {"empresa": empresa, "ref": "Residencial Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"],
        "internas": ["Academia"],
        "plantas": ["Apartamento Tipo"],
        "desconto_pct": desconto,
        "desconto_label": "parceria" if desconto else None,
        "estrategia": estrategia,
        "mostrar_precos_individuais": False,
        "_avisos": [],
    }


def _prep(db):
    aplicar_schema(db)
    semear_precos(db)


def test_levantar_planilha_precos_do_banco(db):
    _prep(db)
    out = svc.levantar(db, _estrutura())
    orc = out["fechado"]["orcamento"]
    assert out["estrategia_usada"] == "planilha"
    assert orc["externas"]["itens"][0]["preco"] == 3000  # fachada, preço do NEON
    assert orc["total_imagens"] == 3


def test_levantar_com_desconto(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(desconto=10.0))
    fin = out["fechado"]["financeiro"]
    assert fin["desconto_pct"] == 10.0
    assert fin["total"] == pytest.approx(fin["subtotal"] * 0.9)
    assert fin["rotulo"] == "parceria"


def test_levantar_auto_usa_historico_quando_cliente_existe(db):
    _prep(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 1800, "total_imagens": 1,
            "externas": {"nome": "externas", "qtd": 0, "total": 0, "itens": []},
            "internas": {"nome": "internas", "qtd": 1, "total": 1800,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1800,
                                    "fonte": "manual"}]},
            "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []},
        },
        "financeiro": {"subtotal": 1800, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 1800.0, "rotulo": ""},
    })
    est = _estrutura(estrategia="auto", empresa="BRNPAR")
    est["externas"] = []
    est["plantas"] = []
    est["internas"] = ["Perspectiva Academia"]
    out = svc.levantar(db, est)
    assert out["estrategia_usada"].startswith("historico")
    assert out["fechado"]["orcamento"]["internas"]["itens"][0]["preco"] == 1800


def test_levantar_auto_sem_historico_cai_na_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="auto", empresa="CLIENTE NOVO"))
    assert out["estrategia_usada"] == "planilha"


def test_levantar_historico_sem_cliente_avisa_e_usa_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="historico", empresa="SEM HISTORICO"))
    assert out["estrategia_usada"] == "planilha"
    assert any("histórico" in a.lower() for a in out["avisos"])


def test_gerar_salva_docx_e_proposta(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)  # sem R2
    out = svc.gerar(db, _estrutura(desconto=10.0), tmp_path)

    assert out["proposta_id"] >= 1
    docx = Path(out["docx_path"])
    assert docx.exists() and docx.name == f"proposta_{out['proposta_id']}.docx"
    assert out["docx_url"] is None

    with db.cursor() as cur:
        cur.execute("SELECT subtotal, docx_url FROM propostas WHERE id = %s",
                    (out["proposta_id"],))
        subtotal, docx_url = cur.fetchone()
    assert subtotal == out["fechado"]["orcamento"]["subtotal"]
    assert docx_url is None


def test_gerar_com_r2_grava_url(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: f"https://r2.exemplo/{chave}")
    out = svc.gerar(db, _estrutura(), tmp_path)
    assert out["docx_url"] == f"https://r2.exemplo/propostas/proposta_{out['proposta_id']}.docx"
    with db.cursor() as cur:
        cur.execute("SELECT docx_url FROM propostas WHERE id = %s", (out["proposta_id"],))
        assert cur.fetchone()[0] == out["docx_url"]
```

- [ ] **Step 2: Rodar e ver falhar**

Pré-requisito: `docker compose up -d db-test`.
Run: `pytest tests/servicos/test_proposta.py -v`
Expected: FAIL (ModuleNotFoundError: app.servicos).

- [ ] **Step 3: Adicionar `atualizar_docx_url` ao repo**

Em `aut-proposta/app/db/repo_propostas.py`, acrescentar ao final:

```python
def atualizar_docx_url(conn: psycopg.Connection, proposta_id: int, docx_url: str) -> None:
    """Grava a URL do .docx (R2) numa proposta já salva."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE propostas SET docx_url = %s WHERE id = %s",
                (docx_url, proposta_id),
            )
```

- [ ] **Step 4: Implementar `proposta.py`**

`aut-proposta/app/servicos/__init__.py` vazio. `aut-proposta/app/servicos/proposta.py`:

```python
"""Orquestração de uma proposta: NEON -> orçamento -> .docx -> R2 -> NEON.

Único lugar que decide a estratégia (planilha × histórico) e o único caminho
de produção que monta TabelaPrecos — sempre via carregar_tabela_precos(conn).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from app.db.repo_precos import carregar_tabela_precos
from app.db.repo_propostas import atualizar_docx_url, salvar_proposta, upsert_cliente
from app.docx.gerador import gerar_docx
from app.dominio.descontos import Desconto
from app.dominio.orcamento import fechar_orcamento, orcar_pela_planilha
from app.historico.historico import Historico
from app.historico.orcamento_historico import orcar_pelo_historico
from app.storage.r2 import enviar_docx


def _descricoes(estrutura: dict[str, Any]) -> dict[str, list[str]]:
    return {cat: estrutura.get(cat, []) for cat in ("externas", "internas", "plantas")}


def levantar(conn: psycopg.Connection, estrutura: dict[str, Any]) -> dict[str, Any]:
    """Resolve estratégia e preços (NEON) e devolve o orçamento fechado."""
    avisos = list(estrutura.get("_avisos", []))
    tabela = carregar_tabela_precos(conn)
    descricoes = _descricoes(estrutura)
    empresa = estrutura["cliente"]["empresa"]
    pedida = estrutura.get("estrategia", "auto")

    historico = Historico(conn)
    orc = None
    if pedida == "historico" or (pedida == "auto" and historico.tem_cliente(empresa)):
        orc = orcar_pelo_historico(historico, empresa, descricoes, tabela)
        if orc is None and pedida == "historico":
            avisos.append(f"Cliente '{empresa}' não tem histórico — usei a tabela de planilha.")
    if orc is None:
        orc = orcar_pela_planilha(descricoes, tabela)

    desconto = None
    if estrutura.get("desconto_pct", 0):
        desconto = Desconto(
            tipo="percentual",
            valor=float(estrutura["desconto_pct"]),
            rotulo=estrutura.get("desconto_label") or "",
        )

    return {
        "cliente": estrutura["cliente"],
        "fechado": fechar_orcamento(orc, desconto),
        "estrategia_usada": orc.estrategia,
        "avisos": avisos,
    }


def gerar(conn: psycopg.Connection, estrutura: dict[str, Any], dir_saida: Path) -> dict[str, Any]:
    """Levanta, persiste no NEON, gera o .docx e tenta subir no R2."""
    lev = levantar(conn, estrutura)
    cliente = lev["cliente"]
    fechado = lev["fechado"]

    cliente_id = upsert_cliente(conn, cliente["empresa"], cliente.get("contato"))
    proposta_id = salvar_proposta(conn, cliente_id, fechado, referencia=cliente.get("ref"))

    docx_path = Path(dir_saida) / f"proposta_{proposta_id}.docx"
    gerar_docx(
        cliente,
        fechado,
        docx_path,
        mostra_precos_individuais=bool(estrutura.get("mostrar_precos_individuais")),
    )

    chave = f"propostas/proposta_{proposta_id}.docx"
    docx_url = enviar_docx(docx_path, chave)
    if docx_url:
        atualizar_docx_url(conn, proposta_id, docx_url)
    else:
        lev["avisos"].append("Upload no R2 indisponível — use o download direto da API.")

    return {
        "proposta_id": proposta_id,
        "docx_path": str(docx_path),
        "docx_url": docx_url,
        "fechado": fechado,
        "avisos": lev["avisos"],
    }
```

- [ ] **Step 5: Rodar e ver passar (suíte inteira)**

Run: `pytest -v`
Expected: PASS — todos os anteriores + 7 novos (com o Docker no ar; os de banco pulam sem ele).

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/app/servicos/ aut-proposta/app/db/repo_propostas.py aut-proposta/tests/servicos/
git commit -m "feat(proposta): serviço de orquestração (NEON -> docx -> R2)"
```

---

### Task 6: API FastAPI (auth + rotas)

**Files:**
- Create: `aut-proposta/app/api/__init__.py`
- Create: `aut-proposta/app/api/main.py`
- Test: `aut-proposta/tests/api/__init__.py`, `aut-proposta/tests/api/test_api.py`

**Interfaces:**
- Consumes: `app.ia.parser.parse`, `app.servicos.proposta.{levantar, gerar}`, `app.db.conexao.get_conn`, env `API_TOKEN`, env `PROPOSTAS_DIR` (default `saidas/` relativo ao cwd).
- Produces (rotas):
  - `GET /saude` → `{"ok": true}` — sem auth.
  - `POST /levantamento` body `{"texto": str}` → interpreta com `parse`, precifica com `levantar`; resposta `{"estrutura": {...}, "fechado": {...}, "estrategia_usada": str, "avisos": [...]}` — com auth.
  - `POST /propostas` body `{"texto": str}` OU `{"estrutura": {...}}` (estrutura já revisada pelo usuário no preview) → `gerar`; resposta `{"proposta_id", "docx_url", "download", "fechado", "avisos"}` onde `download = "/propostas/{id}/docx"` — com auth.
  - `GET /propostas/{id}/docx` → devolve o arquivo `.docx` (FileResponse) — com auth; 404 se não existir.
- Auth: dependency `verificar_token` — sem env `API_TOKEN` → 503 `{"detail": "API_TOKEN não configurado"}`; header ausente/errado → 401.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/api/__init__.py` vazio. `aut-proposta/tests/api/test_api.py`:

```python
"""Testes da API com TestClient. Banco real (fixture db); parser mockado onde útil."""
import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api.main import app
from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db

TOKEN = "token-de-teste"
HEAD = {"Authorization": f"Bearer {TOKEN}"}

TEXTO = """Cliente: GALLI, ref Residencial Aurora, a/c Daniel
Externas: Fachada vista da calçada
Internas: Academia
Plantas: Apartamento Tipo
10% de desconto, preço de planilha"""


@pytest.fixture
def cliente_api(db, tmp_path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("PROPOSTAS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # força parser local
    monkeypatch.setattr("app.servicos.proposta.enviar_docx", lambda c, k: None)
    aplicar_schema(db)
    semear_precos(db)
    # A API abre a própria conexão; aponta para o banco de teste.
    monkeypatch.setattr(api_main, "_abrir_conn", lambda: db)
    monkeypatch.setattr(api_main, "_fechar_conn", lambda conn: None)
    return TestClient(app)


def test_saude_sem_auth(cliente_api):
    r = cliente_api.get("/saude")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_sem_token_configurado_da_503(db, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    c = TestClient(app)
    r = c.post("/levantamento", json={"texto": "x"})
    assert r.status_code == 503


def test_token_errado_da_401(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": "x"},
                         headers={"Authorization": "Bearer errado"})
    assert r.status_code == 401


def test_levantamento_precifica(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["estrutura"]["cliente"]["empresa"] == "GALLI"
    assert corpo["fechado"]["orcamento"]["externas"]["itens"][0]["preco"] == 3000
    assert corpo["fechado"]["financeiro"]["desconto_pct"] == 10.0
    assert corpo["estrategia_usada"] == "planilha"


def test_gerar_proposta_completa(cliente_api):
    r = cliente_api.post("/propostas", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    pid = corpo["proposta_id"]
    assert corpo["download"] == f"/propostas/{pid}/docx"
    assert corpo["docx_url"] is None  # R2 mockado como indisponível

    r2 = cliente_api.get(corpo["download"], headers=HEAD)
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert len(r2.content) > 1000  # docx de verdade


def test_gerar_por_estrutura_revisada(cliente_api):
    estrutura = {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    r = cliente_api.post("/propostas", json={"estrutura": estrutura}, headers=HEAD)
    assert r.status_code == 200
    assert r.json()["fechado"]["orcamento"]["subtotal"] == 3000


def test_download_inexistente_404(cliente_api):
    r = cliente_api.get("/propostas/99999/docx", headers=HEAD)
    assert r.status_code == 404


def test_propostas_sem_texto_nem_estrutura_422(cliente_api):
    r = cliente_api.post("/propostas", json={}, headers=HEAD)
    assert r.status_code == 422
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/api/test_api.py -v`
Expected: FAIL (ModuleNotFoundError: app.api).

- [ ] **Step 3: Implementar `main.py`**

`aut-proposta/app/api/__init__.py` vazio. `aut-proposta/app/api/main.py`:

```python
"""API HTTP do serviço de propostas (consumida pelo hub flyingstudio-tools).

Auth simples de serviço interno: Bearer token fixo comparado com API_TOKEN.
Sem API_TOKEN no ambiente as rotas protegidas devolvem 503 — nunca abrem.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator

from app.db.conexao import get_conn
from app.ia.parser import parse
from app.servicos.proposta import gerar, levantar

app = FastAPI(title="Automação de Proposta — Flying Studio")

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _dir_saida() -> Path:
    return Path(os.getenv("PROPOSTAS_DIR", "saidas"))


# Indireção para os testes injetarem a conexão do fixture db.
def _abrir_conn():
    return get_conn()


def _fechar_conn(conn) -> None:
    conn.close()


def verificar_token(request: Request) -> None:
    esperado = os.getenv("API_TOKEN")
    if not esperado:
        raise HTTPException(503, "API_TOKEN não configurado")
    recebido = request.headers.get("Authorization", "")
    if not hmac.compare_digest(recebido, f"Bearer {esperado}"):
        raise HTTPException(401, "Token inválido")


class CorpoLevantamento(BaseModel):
    texto: str


class CorpoProposta(BaseModel):
    texto: str | None = None
    estrutura: dict | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if self.texto is None and self.estrutura is None:
            raise ValueError("Envie 'texto' ou 'estrutura'.")
        return self


@app.get("/saude")
def saude():
    return {"ok": True}


@app.post("/levantamento", dependencies=[Depends(verificar_token)])
def rota_levantamento(corpo: CorpoLevantamento):
    estrutura = parse(corpo.texto)
    conn = _abrir_conn()
    try:
        lev = levantar(conn, estrutura)
    finally:
        _fechar_conn(conn)
    return {
        "estrutura": estrutura,
        "fechado": lev["fechado"],
        "estrategia_usada": lev["estrategia_usada"],
        "avisos": lev["avisos"],
    }


@app.post("/propostas", dependencies=[Depends(verificar_token)])
def rota_gerar(corpo: CorpoProposta):
    estrutura = corpo.estrutura if corpo.estrutura is not None else parse(corpo.texto)
    conn = _abrir_conn()
    try:
        out = gerar(conn, estrutura, _dir_saida())
    finally:
        _fechar_conn(conn)
    return {
        "proposta_id": out["proposta_id"],
        "docx_url": out["docx_url"],
        "download": f"/propostas/{out['proposta_id']}/docx",
        "fechado": out["fechado"],
        "avisos": out["avisos"],
    }


@app.get("/propostas/{proposta_id}/docx", dependencies=[Depends(verificar_token)])
def rota_download(proposta_id: int):
    caminho = _dir_saida() / f"proposta_{proposta_id}.docx"
    if not caminho.exists():
        raise HTTPException(404, "Proposta não encontrada")
    return FileResponse(caminho, media_type=MIME_DOCX,
                        filename=f"proposta_{proposta_id}.docx")
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `pytest -v`
Expected: PASS — tudo verde (com Docker no ar). Confira que NÃO houve chamadas de rede (OpenAI sem chave → local; R2 monkeypatched).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/api/ aut-proposta/tests/api/
git commit -m "feat(proposta): API FastAPI (levantamento, geração, download, auth)"
```

---

### Task 7: Docker, env de exemplo e documentação

**Files:**
- Create: `aut-proposta/Dockerfile`
- Create: `aut-proposta/.env.example`
- Create: `aut-proposta/README.md`
- Modify: `aut-proposta/.gitignore` (ignorar `saidas/`)

**Interfaces:**
- Consumes: `app.api.main:app`.
- Produces: imagem Docker rodando `uvicorn` na porta 8000 (padrão Railway); documentação de setup/rotas/envs.

- [ ] **Step 1: Criar `Dockerfile`**

`aut-proposta/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /srv/aut-proposta

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Criar `.env.example` e ignorar `saidas/`**

`aut-proposta/.env.example`:

```bash
# Banco (NEON em produção; local via docker compose nos testes)
DATABASE_URL="postgresql://usuario:senha@host/db?sslmode=require"

# Auth da API (obrigatório — sem ele a API devolve 503)
API_TOKEN="troque-por-um-token-longo"

# OpenAI (opcional — sem chave, parser local assume)
OPENAI_API_KEY=""
OPENAI_MODEL="gpt-4o-mini"

# Cloudflare R2 (opcional — sem credenciais, só download direto)
R2_ACCOUNT_ID=""
R2_ACCESS_KEY_ID=""
R2_SECRET_ACCESS_KEY=""
R2_BUCKET=""
R2_PUBLIC_BASE_URL=""

# Diretório local dos .docx gerados
PROPOSTAS_DIR="saidas"
```

Em `aut-proposta/.gitignore`, acrescentar a linha:

```
saidas/
```

- [ ] **Step 3: Criar `README.md`**

`aut-proposta/README.md`:

```markdown
# Automação de Proposta — Flying Studio

Serviço FastAPI que gera propostas comerciais em `.docx` timbrado: uma IA
(OpenAI, com fallback regex offline) interpreta o pedido em texto livre, o
código precifica pela tabela oficial (NEON) ou pelo histórico do cliente,
aplica descontos e gera o documento, subindo o arquivo no Cloudflare R2.

**Princípio-chave:** a IA nunca produz um número. Preço, soma e desconto são
código determinístico e testado.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # preencha as variáveis
```

Testes (os de banco usam Postgres local):

```bash
docker compose up -d db-test
pytest
```

Rodar a API:

```bash
uvicorn app.api.main:app --reload
```

Seed da tabela de preços no NEON (uma vez, ou quando a planilha mudar):

```bash
python -m scripts.seed_precos
```

## Rotas

| Rota | Corpo | Faz |
|---|---|---|
| `GET /saude` | — | healthcheck (sem auth) |
| `POST /levantamento` | `{"texto"}` | interpreta + precifica (preview, não grava) |
| `POST /propostas` | `{"texto"}` ou `{"estrutura"}` | grava no NEON, gera `.docx`, sobe no R2 |
| `GET /propostas/{id}/docx` | — | download direto do `.docx` |

Auth: header `Authorization: Bearer $API_TOKEN` em todas menos `/saude`.

## Arquitetura

`app/dominio/` (puro: preços, orçamento, descontos) · `app/db/` (NEON) ·
`app/historico/` (2º levantamento) · `app/ia/` (parser OpenAI/regex) ·
`app/docx/` (gerador timbrado) · `app/storage/` (R2) · `app/servicos/`
(orquestração) · `app/api/` (FastAPI).
```

- [ ] **Step 4: Build da imagem como verificação**

Run (a partir de `aut-proposta/`, com Docker no ar): `docker build -t aut-proposta .`
Expected: build OK. Sanidade opcional: `docker run --rm -p 8000:8000 -e API_TOKEN=x aut-proposta` e `curl http://localhost:8000/saude` → `{"ok":true}`.
Se o Docker não estiver disponível, registre no relatório e siga — o build será validado no deploy.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `pytest`
Expected: tudo verde (nenhum teste novo nesta task, só garantia de que nada quebrou).

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/Dockerfile aut-proposta/.env.example aut-proposta/README.md aut-proposta/.gitignore
git commit -m "chore(proposta): Dockerfile, .env.example e README do serviço"
```

---

## Verificação final (fora das tasks — controlador)

Com `.env` real preenchido (NEON + OPENAI_API_KEY + R2 + API_TOKEN): subir `uvicorn`, rodar um `POST /levantamento` e um `POST /propostas` reais com o caso GALLI, conferir o `.docx` gerado, a URL do R2 e a linha em `propostas` no NEON.

## Self-Review

**Cobertura do spec (design §§3-8, parte docx/IA/API/storage):**
- `docx/` gera timbrado com conteúdo fixo + flexível (§4, §6 passo 5) → Tasks 1-2 (formatos + gerador; teste reabre o documento e valida conteúdo, §8). ✔
- `ia/` interpreta fala → itens estruturados, OpenAI + fallback regex (§4, §7) → Task 3; IA nunca vê/produz preço (princípio-chave). ✔
- `storage/` sobe no R2 e devolve URL; falha → download direto (§4, §7) → Task 4 + fallback no serviço (Task 5) e rota de download (Task 6). ✔
- Orquestração com os 2 levantamentos e sugestão do histórico (§6 passos 3-5) → Task 5 (`levantar`: planilha/historico/auto; `gerar`: NEON+docx+R2). ✔
- API REST autenticada consumida pelo hub (§3) → Task 6 (Bearer/`API_TOKEN`, 503 sem config). ✔
- FastAPI + Docker padrão LUMEN/Railway (§2) → Task 7 (Dockerfile porta 8000). ✔
- Erros (§7): OpenAI fora → parser local (Task 3 `parse`); item não classificado → `_default` já vem do domínio (Plano 1); R2 falhando → `docx_url=None` + aviso + download direto (Tasks 4-6). ✔
- **Fora deste plano (intencional):** UI no hub (Plano 4); PDF; extras tour/filmes/apps/drone; upload de imagens (§9).

**Minors deferidos do Plano 2 resolvidos aqui:** "sempre injetar TabelaPrecos do banco" → `levantar` é o único caminho de produção e usa `carregar_tabela_precos(conn)` (constraint global). Demais (CATEGORIAS 4×, ON CONFLICT, `_ultima` 3×, `_formata_descricao` privado, porta 5432) seguem deferidos — nenhum é pré-requisito destas tasks.

**Placeholders:** nenhum TBD; todo código presente em cada step.

**Consistência de tipos/nomes:**
- `fechado` (`{"orcamento","financeiro"}`) flui de `fechar_orcamento` (Plano 1) → `gerar_docx` (Task 2) → `salvar_proposta` (Plano 2) → resposta da API (Task 6) sem conversão. Chaves de item `{"descricao","preco","fonte"}` idem. ✔
- Estrutura do parser (Task 3) = entrada de `levantar`/`gerar` (Task 5) = `estrutura` aceita pela API (Task 6): mesmas chaves (`cliente{empresa,ref,contato}`, listas por categoria, `desconto_pct`, `desconto_label`, `estrategia`, `mostrar_precos_individuais`, `_avisos`). ✔
- `enviar_docx(caminho, chave)` (Task 4) é importado por nome em `servicos/proposta.py` (Task 5) — monkeypatch nos testes usa `app.servicos.proposta.enviar_docx` (o nome importado, não o de origem). ✔
- `atualizar_docx_url` definido na Task 5 antes do uso na mesma task. ✔
- Testes de API monkeypatcham `api_main._abrir_conn`/`_fechar_conn` — nomes definidos na Task 6. ✔

**Pureza do domínio:** nenhuma task toca `app/dominio/`; `gerar_docx` consome dicts; `orcar_pela_planilha`/`fechar_orcamento` recebem a tabela por parâmetro. ✔
