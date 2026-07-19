"""Gera o .docx da proposta no modelo oficial Flying Studio (PROPOSTA_EXEMPLO).

Estrutura fiel ao exemplo: cabeçalho da proposta, 1 – Apresentação (três
parágrafos institucionais), 2 – Itens/Investimentos (listas numeradas com
"Valor total" por categoria, investimento e forma de pagamento), 3 – Prazos /
Solicitações / Considerações / Entregas, data e "De acordo". Consome a
estrutura de fechar_orcamento ({"orcamento": ..., "financeiro": ...}) e usa o
papel timbrado versionado em app/docx/timbrado/ quando existir.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.docx.formatos import brl, data_extenso, extenso

TIMBRADO_PATH = Path(__file__).resolve().parent / "timbrado" / "TIMBRADO_FLYINGSTUDIO.docx"

FONTE = "Calibri"
COR_TEXTO = RGBColor(0x1F, 0x23, 0x30)

ROTULOS_CATEGORIA = {
    "externas": "Ilustrações Externas",
    "internas": "Ilustrações Internas",
    "plantas": "Plantas Humanizadas 2D",
}

APRESENTACAO = [
    ("Nascemos para dar forma ao invisível",
     "Em 9 de maio de 2011, abrimos nossas portas com uma crença simples e poderosa: "
     "“uma imagem vale mais do que mil palavras”. Hoje, somos a ponte entre a ideia e a "
     "venda, provamos que a nossa arte não é apenas ilustrar a realidade, mas fazer o "
     "cliente vivenciar o futuro."),
    ("Muito além das perspectivas",
     "Esse sempre foi o nosso lema e, secretamente, a nossa profecia. Ao longo de quase "
     "duas décadas, acompanhamos o nascimento de centenas de empreendimentos e entendemos "
     "o que faz um projeto vender, o que atrai o olhar do investidor, o que acelera um "
     "lançamento e o que transforma um terreno em um verdadeiro case de sucesso e desejo."),
    ("Nossa evolução foi um despertar",
     "A arte sempre será o nosso compasso, mas toda essa trajetória nos trouxe algo ainda "
     "mais valioso: a precisão mercadológica. Percebemos que uma imagem impecável é o "
     "convite perfeito, mas o nosso objetivo tornou-se assumir o controle de toda a "
     "experiência de compra. Nós não apenas ilustramos o amanhã; nós fazemos com que ele "
     "seja vivenciado. Para tangibilizar o amanhã, desenhamos um universo onde a tecnologia "
     "une encantamento e estratégia. A gestão fluida dos nossos aplicativos garante o "
     "controle absoluto da apresentação, preparando o terreno para o nosso D.sbrave, uma "
     "poderosa ferramenta de imersão que permite ao cliente caminhar e já projetar a sua "
     "vida no futuro lar, explorando cada detalhe em 360º. E nós fomos além: através da "
     "Realidade Aumentada, materializamos o projeto direto na mesa de negociação, enquanto "
     "nossas Salas Imersivas transformam o estande de vendas em um verdadeiro portal "
     "sensorial, arrebatando o cliente no momento decisivo da compra. Somamos tudo isso a "
     "grandiosidade dos nossos filmes cinematográficos e conceituais, que conectam metros "
     "quadrados a narrativas reais de vida. O visual atrai, mas é a imersão completa que "
     "fecha a venda."),
]

SOLICITACOES = [
    ("Arquitetura:", "• Plantas • Elevação da Fachada • Estudo de Cores da Fachada • Cortes;"),
    ("Paisagismo:", "• Implantação • Detalhamentos • Especificação de Revestimentos • Estudo de "
                    "Vegetação com Especificação de Espécies • Referências do Mobiliário;"),
    ("Decoração:", "• Plantas com Layout • Desenhos de Pisos • Elevações de Paredes • "
                   "Especificações de materiais • Projeto de Forro e Iluminação • Descrição ou "
                   "book de mobiliários."),
]

OBS_SOLICITACOES = (
    "OBS: Na ausência de qualquer um dos itens necessários ao desenvolvimento do projeto, a "
    "NID Studio poderá ser consultada para propor soluções de conceito, layout, ambientação, "
    "fachada, materiais, mobiliário, decoração ou PDV, conforme a necessidade identificada, "
    "por meio de um escopo complementar a ser avaliado e apresentado à parte."
)

CONSIDERACOES = [
    ("Etapas e Tiros de Aprovação:",
     "Esta proposta contempla o envio inicial do tiro de Shade, seguido do tiro de "
     "apresentação denominado “R00”. Estão inclusas no escopo 03 (três) rodadas de revisões, "
     "denominadas “R01”, “R02” e “R03”, culminando na entrega final denominada “HR” "
     "(High Resolution)."),
    ("Ajustes Finos e Adicionais:",
     "Damos ênfase que, a partir do tiro “R00”, as rodadas seguintes consistem exclusivamente "
     "em ajustes finos. A partir de um eventual quarto tiro de apresentação (denominado "
     "“R04”), será cobrado um adicional de 25% do valor da imagem por tiro extra solicitado."),
    ("Plataforma Oficial de Revisão:",
     "Para garantir a organização, a agilidade e a precisão técnica das refações, todo o "
     "processo de feedback, comentários e aprovações (tanto dos filmes quanto das imagens 3D) "
     "será realizado exclusivamente através do software especializado Frame.io/Adobe."),
    ("Mecânica de Apontamentos:",
     "A Contratada fornecerá à Contratante um link de acesso seguro à plataforma. Através do "
     "Frame.io/Adobe, o cliente poderá inserir comentários, desenhar marcações, anexar "
     "informações (pdf, foto, dwg, etc) e solicitar ajustes exatamente no frame do vídeo ou "
     "no ponto específico da imagem estática que deseja alterar, eliminando ruídos de "
     "comunicação. “Para garantir agilidade e facilitar o processo de adaptação, sugerimos a "
     "visualização do guia prático em vídeo de como realizar revisões dentro da plataforma.”"),
    ("Alterações de Projeto:",
     "Quaisquer alterações nos projetos originais (sejam de design de interiores, "
     "arquitetônico ou paisagismo) fornecidos inicialmente implicam em cobranças extras de "
     "modelagem, que serão orçadas e aprovadas em comum acordo."),
    ("Refação e Remodelagem:",
     "No decorrer das rodadas de tiros, havendo mudanças significativas no projeto que "
     "resultem na perda de até 50% da imagem já construída (sendo necessária a remodelagem "
     "ou retrocesso na etapa de produção), o trabalho será considerado e cobrado como uma "
     "imagem nova."),
    ("Paralisação do Projeto:",
     "Em caso de paralisação total ou parcial do escopo por um período de até 60 (sessenta) "
     "dias, deverá ser feito o acerto financeiro imediato das etapas já executadas. Para este "
     "cálculo de acerto, considera-se que cada tiro enviado após a aprovação do R00 "
     "corresponde a 25% do valor total da imagem."),
    ("Cancelamento:",
     "Em caso de descontinuidade e cancelamento do produto ou lançamento por qualquer motivo "
     "por parte da Contratante, considera-se justa e devida a quitação integral do saldo "
     "previsto nesta proposta."),
    ("Direitos de Uso:",
     "A Contratada cede à Contratante os direitos de uso das imagens produzidas para uso "
     "promocional em todo o seu material publicitário, única e exclusivamente vinculadas ao "
     "empreendimento contratado, não havendo débitos/atrasos financeiros."),
]

ENTREGA_FINAL = [
    ("Formato e Envio:",
     "Todo o material finalizado será enviado digitalmente via servidor FTP, link seguro "
     "para download ou cadastrados no Frame.io/Adobe."),
    ("Resolução das Imagens Estáticas:",
     "As imagens finais (denominadas “HR”) serão entregues com 6000px em seu lado maior a "
     "300dpi."),
    (None,
     "Caso a Contratante necessite de imagens configuradas para impressões de até 1 (um) "
     "metro, a solicitação deve ser feita com antecedência à renderização final, sem custo "
     "adicional."),
    (None,
     "Para imagens com medidas de impressão superiores a 1 (um) metro (como outdoors ou "
     "grandes painéis), favor consultar previamente os valores adicionais de render, com "
     "custo estimado de 20% do valor da imagem, consultar."),
    ("Resolução das Animações/Filmes:",
     "Os passeios virtuais e filmes integrados serão entregues finalizados no formato "
     "Full HD a 30 FPS ou propostas via RINNO FILMS, consultar."),
]

PARCELAS_PAGAMENTO = (
    (50, "Na aprovação desta Proposta"),
    (25, "Envio dos Shades"),
    (25, "Envio HR — Imagens finais"),
)


# ---------- helpers ----------


def _run(p, texto, *, bold=False, italic=False, size=11):
    r = p.add_run(texto)
    r.font.name = FONTE
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    r.font.color.rgb = COR_TEXTO
    return r


def _par(doc, *, alinhamento=None, antes=0, depois=6, recuo=None):
    p = doc.add_paragraph()
    if alinhamento is not None:
        p.alignment = alinhamento
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(depois)
    p.paragraph_format.line_spacing = 1.15
    if recuo is not None:
        p.paragraph_format.left_indent = Cm(recuo)
    return p


def _titulo_secao(doc, numero: str, titulo: str):
    """Ex.: "1  – APRESENTAÇÃO FLYING STUDIO" (bold)."""
    p = _par(doc, antes=10, depois=8)
    _run(p, f"{numero}  – {titulo}", bold=True, size=11)
    return p


def _subtitulo(doc, texto: str, *, complemento: str | None = None):
    p = _par(doc, antes=8, depois=6)
    _run(p, texto, bold=True, size=11)
    if complemento:
        _run(p, f" {complemento}", size=11)
    return p


def _bullet(doc, rotulo: str | None, texto: str):
    p = _par(doc, depois=6, recuo=1.0)
    p.paragraph_format.first_line_indent = Cm(-0.5)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _run(p, "•   ", size=11)
    if rotulo:
        _run(p, f"{rotulo} ", bold=True, size=11)
    _run(p, texto, size=11)
    return p


def _limpar_corpo(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


# ---------- documento ----------


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
        secao.top_margin = Cm(2.3)
        secao.bottom_margin = Cm(2.5)
        p = secao.header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(p, "FLYING studio", bold=True, size=12)

    # ===== Cabeçalho da proposta =====
    p = _par(doc, depois=2)
    _run(p, "PROPOSTA DE IMAGENS, FILMES E TECNOLOGIAS 3D", bold=True, size=11)
    p = _par(doc, depois=2)
    _run(p, f"{cliente['empresa'].upper()} - REF: {cliente['ref'].upper()}", bold=True, size=11)
    p = _par(doc, depois=10)
    _run(p, f"A/C: {cliente['contato'].upper()}", bold=True, size=11)

    # ===== 1 – Apresentação =====
    _titulo_secao(doc, "1", "APRESENTAÇÃO FLYING STUDIO")
    for lead, corpo in APRESENTACAO:
        p = _par(doc, depois=8)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _run(p, f"{lead} - ", bold=True, size=11)
        _run(p, corpo, size=11)

    # ===== 2 – Itens / Investimentos =====
    _titulo_secao(doc, "2", "ITENS A SEREM DESENVOLVIDOS / INVESTIMENTOS:")

    sub = 0
    for cat in ("externas", "internas", "plantas"):
        bloco = orc[cat]
        if not bloco["qtd"]:
            continue
        sub += 1
        _subtitulo(doc, f"2.{sub} {ROTULOS_CATEGORIA[cat]}")
        for idx, item in enumerate(bloco["itens"], start=1):
            p = _par(doc, depois=2, recuo=1.25)
            texto = f"{idx}. {item['descricao']}"
            if mostra_precos_individuais:
                texto += f" — {brl(item['preco'])}"
            _run(p, texto, size=11)
        p = _par(doc, antes=6, depois=8)
        _run(p, "Valor total: ", size=11)
        _run(p, brl(bloco["total"]), bold=True, size=11)

    sub += 1
    _subtitulo(doc, f"2.{sub} INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA DESCRITOS:")
    p = _par(doc, depois=2, recuo=1.25)
    _run(p, brl(fin["total"]).replace("R$", "R$ "), bold=True, size=12)
    p = _par(doc, depois=2, recuo=1.25)
    _run(p, f"({extenso(fin['total'])})", italic=True, size=9)
    if fin["desconto_pct"] > 0:
        rotulo = fin["rotulo"] or f"{fin['desconto_pct']}%"
        p = _par(doc, depois=8, recuo=1.25)
        _run(p, f"Valor bruto: {brl(fin['subtotal'])}  ·  Desconto ({rotulo}): "
                f"-{brl(fin['desconto_valor'])}", size=9)

    sub += 1
    _subtitulo(doc, f"2.{sub} FORMA DE PAGAMENTO:")
    for pct, marco in PARCELAS_PAGAMENTO:
        v = fin["total"] * (pct / 100.0)
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"{pct}% – {marco} ({brl(v)})", size=11)

    # ===== 3 – Prazos / Solicitações / Considerações / Entregas =====
    _titulo_secao(doc, "3", "PRAZOS / SOLICITAÇÕES / CONSIDERAÇÕES / ENTREGAS")

    p = _par(doc, depois=2, recuo=1.0)
    _run(p, "3.1 Shades", bold=True, size=11)
    _run(p, " – 20 (Vinte) dias", size=11)
    p = _par(doc, depois=2, recuo=1.0)
    _run(p, "1º Tiro", bold=True, size=11)
    _run(p, " – 15 (Quinze) dias após a aprovação dos Shades,", size=11)
    p = _par(doc, depois=8, recuo=1.0)
    _run(p, "Revisões", bold=True, size=11)
    _run(p, " – 10 (Dez) dias para contemplar e enviar novos tiros.", size=11)

    _subtitulo(doc, "3.2 SOLICITAÇÕES:",
               complemento="Arquivos e definições necessários à execução do serviço.")
    for rotulo, texto in SOLICITACOES:
        p = _par(doc, depois=2, recuo=1.0)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _run(p, f"{rotulo} ", bold=True, size=11)
        _run(p, texto, size=11)
    p = _par(doc, antes=6, depois=8, recuo=1.0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _run(p, OBS_SOLICITACOES, size=11)

    _subtitulo(doc, "3.3 CONSIDERAÇÕES IMAGENS:")
    for rotulo, texto in CONSIDERACOES:
        _bullet(doc, rotulo, texto)

    _subtitulo(doc, "3.4 ENTREGA FINAL:")
    for rotulo, texto in ENTREGA_FINAL:
        _bullet(doc, rotulo, texto)

    # ===== Assinatura =====
    p = _par(doc, antes=16, depois=12)
    _run(p, f"São Paulo, {data_extenso(data)}.", size=11)
    p = _par(doc, depois=2)
    _run(p, "De acordo,", size=11)
    p = _par(doc, depois=0)
    _run(p, cliente["empresa"].upper(), bold=True, size=11)

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida
