"""Primitivas de escrita compartilhadas pelos geradores das três empresas.

Aqui fica só o que é igual em Flying, Rinno e NID: tipografia, parágrafos,
títulos, bullets, abertura do timbrado e os blocos de cabeçalho/assinatura.
A estrutura do documento — quantas seções, em que ordem, com que texto — é
de cada empresa, em `app/docx/flying.py`, `rinno.py` e `nid.py`.

Os textos ricos são listas de segmentos (texto, estilo) com estilo em
{'', 'b', 'i', 'u', 'iu'} — b=negrito, i=itálico, u=sublinhado.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

from app.docx.formatos import brl, data_extenso, extenso
from app.empresas import Empresa

TIMBRADO_DIR = Path(__file__).resolve().parent / "timbrado"

FONTE = "Calibri"
COR_TEXTO = RGBColor(0x1F, 0x23, 0x30)

Seg = tuple[str, str]  # (texto, estilo)


def timbrado_de(empresa: Empresa) -> Path:
    return TIMBRADO_DIR / empresa.timbrado


# ---------- tipografia ----------


def _run(p, texto, *, estilo=""):
    r = p.add_run(texto)
    r.font.name = FONTE
    r.font.size = Pt(11)
    r.font.color.rgb = COR_TEXTO
    r.bold = "b" in estilo
    r.italic = "i" in estilo
    r.underline = "u" in estilo
    return r


def _rich(p, segs: list[Seg]):
    for texto, estilo in segs:
        _run(p, texto, estilo=estilo)
    return p


def _par(doc, *, antes=0, depois=6, recuo=None, justificado=False):
    p = doc.add_paragraph()
    if justificado:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(depois)
    p.paragraph_format.line_spacing = 1.15
    if recuo is not None:
        p.paragraph_format.left_indent = Cm(recuo)
    return p


def _titulo_secao(doc, numero: str, titulo: str):
    p = _par(doc, antes=10, depois=8)
    _run(p, f"{numero}  – {titulo}", estilo="b")
    return p


def _subtitulo(doc, texto: str, *, complemento: str | None = None):
    p = _par(doc, antes=8, depois=6)
    _run(p, texto, estilo="b")
    if complemento:
        _run(p, f" {complemento}", estilo="b")
    return p


def _bullet(doc, segs: list[Seg]):
    p = _par(doc, depois=6, recuo=1.0, justificado=True)
    p.paragraph_format.first_line_indent = Cm(-0.5)
    _run(p, "•   ")
    _rich(p, segs)
    return p


def _limpar_corpo(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


# ---------- documento ----------


def abrir_documento(empresa: Empresa) -> Document:
    """Abre o timbrado da empresa e esvazia o corpo, preservando cabeçalho e
    rodapé (que é onde mora a arte).

    As margens do corpo vêm de `empresa.margens`, não do timbrado: a arte de
    algumas delas sangra a página (a da NID tem margem esquerda zero), e o
    texto herdar isso o jogaria contra a borda.
    """
    caminho = timbrado_de(empresa)
    if caminho.exists():
        doc = Document(str(caminho))
        _limpar_corpo(doc)
    else:
        doc = Document()
        p = doc.sections[0].header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(p, empresa.nome, estilo="b")

    m = empresa.margens
    for secao in doc.sections:
        secao.left_margin = Cm(m.esquerda)
        secao.right_margin = Cm(m.direita)
        secao.top_margin = Cm(m.topo)
        secao.bottom_margin = Cm(m.base)
        _arte_ocupa_a_pagina(secao)
    return doc


def _partes_de_arte(secao):
    """Cabeçalhos e rodapés da seção, incluindo os de primeira página e de
    página par — a NID e a Rinno têm um cabeçalho só para a página 1."""
    for nome in ("header", "first_page_header", "even_page_header",
                 "footer", "first_page_footer", "even_page_footer"):
        parte = getattr(secao, nome, None)
        if parte is not None:
            yield parte


def _arte_ocupa_a_pagina(secao) -> None:
    """Dá ao cabeçalho e ao rodapé a largura da página inteira.

    A arte das três empresas é faixa de sangria — 21 cm de ponta a ponta — mas
    o cabeçalho, por padrão, é uma coluna tão estreita quanto a do texto. Com
    margem de 3 cm de cada lado, sobram 15 cm e 6 cm de arte são cortados: some
    o logo da direita. O recuo negativo, de exatamente a margem, devolve a
    página inteira à faixa sem mexer no texto (que tem o seu próprio recuo).
    """
    for parte in _partes_de_arte(secao):
        for p in parte.paragraphs:
            p.paragraph_format.left_indent = Emu(-secao.left_margin)
            p.paragraph_format.right_indent = Emu(-secao.right_margin)


def cabecalho_proposta(doc, empresa: Empresa, cliente: dict[str, str]) -> None:
    """Título da proposta + CLIENTE - REF + A/C, no padrão das três empresas."""
    p = _par(doc, depois=2)
    _run(p, empresa.titulo_proposta, estilo="b")
    p = _par(doc, depois=2)
    _run(p, f"{cliente['empresa'].upper()} - REF: {cliente['ref'].upper()}", estilo="b")
    p = _par(doc, depois=10)
    _run(p, f"A/C: {cliente['contato'].upper()}", estilo="b")


def bloco_investimento(doc, numero: str, fin: dict, titulo: str | None = None) -> None:
    """Valor fechado da proposta, por extenso como nos modelos oficiais
    ("R$ 59.000,00 (Cinquenta e Nove Mil Reais)").

    Havendo desconto, saem duas linhas, na redação que o grupo usa em TODAS as
    propostas — a antiga "(Valor bruto … · Desconto …)" não é como se escreve:

        Valor total = R$ 60.000,00
        Valor total com desconto especial de 23,3% = R$ 46.000,00 (Quarenta e Seis Mil Reais)

    "DESENVOLVIMENTOS" no plural é como está no modelo oficial das três
    empresas — não é erro de digitação daqui.
    """
    _subtitulo(doc, f"{numero} {titulo or 'INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA DESCRITOS:'}")

    # Proposta de cortesia (100% de desconto): o item mostra o valor, e o
    # investimento sai como a Rinno faz — a palavra, não "R$ 0,00".
    if fin["total"] == 0 and fin["subtotal"] > 0:
        p = _par(doc, depois=8, recuo=1.25)
        _run(p, "CORTESIA", estilo="b")
        return

    if fin["desconto_pct"] > 0:
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"Valor total = {brl(fin['subtotal']).replace('R$', 'R$ ')}")
        p = _par(doc, depois=8, recuo=1.25)
        # Percentual com vírgula, como se escreve em português: 23,3% e não 23.3%.
        pct = f"{fin['desconto_pct']:g}".replace(".", ",")
        _run(p, f"Valor total com desconto especial de {pct}% = "
                f"{brl(fin['total']).replace('R$', 'R$ ')} ({extenso(fin['total'])})")
    else:
        p = _par(doc, depois=8, recuo=1.25)
        _run(p, f"{brl(fin['total']).replace('R$', 'R$ ')} ({extenso(fin['total'])})")


def bloco_pagamento(doc, numero: str, fin: dict, parcelas: tuple[tuple[int, str], ...],
                    vezes: int | None = None) -> None:
    """Forma de pagamento.

    Com `vezes` ("pagamento em 4x"), sai o parcelamento pedido: ato + N-1, em
    valores iguais, como nas propostas ("Em 5x – Ato de R$13.800,00 + 4x de
    13.800,00"). Sem ele, vale o cronograma da empresa, atrelado às etapas.

    Em qualquer um dos dois o valor da parcela é conta feita aqui, nunca texto
    digitado; a última absorve o centavo que a divisão deixa.
    """
    _subtitulo(doc, f"{numero} FORMA DE PAGAMENTO:")
    if vezes and vezes > 1:
        base = round(fin["total"] / vezes, 2)
        ultima = round(fin["total"] - base * (vezes - 1), 2)
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"Em {vezes}x – Ato de {brl(base)} + {vezes - 1}x de "
                f"{brl(ultima) if ultima != base else brl(base)}")
        return
    if vezes == 1:
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"À vista, na aprovação desta Proposta ({brl(fin['total'])})")
        return
    for pct, marco in parcelas:
        v = fin["total"] * (pct / 100.0)
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"{pct}% – {marco} ({brl(v)})")


def assinatura(doc, data: dt.date) -> None:
    p = _par(doc, antes=16, depois=12)
    _run(p, f"São Paulo, {data_extenso(data)}.")
    p = _par(doc, depois=24)
    _run(p, "De acordo,")
    # Linha de assinatura VAZIA — o cliente assina sobre ela no PDF enviado.
    p = _par(doc, depois=0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "_" * 60)


def valor_do_item(preco: int) -> str:
    """Como o valor de um item sai na proposta.

    Serviço sem preço de tabela entra com zero e o valor é combinado depois —
    e "R$0,00" numa proposta enviada é pior do que não dizer nada.
    """
    return brl(preco) if preco else "a definir"


def itens_orcados(orc: dict) -> list[tuple[str, str, dict]]:
    """Categorias com item, na ordem do catálogo: (nome, rótulo, bloco)."""
    meta = orc.get("_categorias") or []
    out = []
    for c in meta:
        bloco = orc.get(c["nome"])
        if bloco and bloco["qtd"]:
            out.append((c["nome"], c["rotulo"], bloco))
    return out
