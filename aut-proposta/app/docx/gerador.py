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
