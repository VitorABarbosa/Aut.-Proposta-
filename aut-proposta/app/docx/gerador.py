"""Gera o .docx da proposta no modelo oficial Flying Studio (PROPOSTA_EXEMPLO).

Fidelidade run a run ao exemplo: estrutura numerada, textos exatos e os
destaques inline (negritos em “R00”/“HR”/Frame.io/NID Studio/etc., itálicos,
sublinhados e as marcações amarelas dos campos do cliente). Os textos ricos
são listas de segmentos (texto, estilo) com estilo em {'', 'b', 'i', 'u',
'iu', 'bh'} — b=negrito, i=itálico, u=sublinhado, h=marca-texto amarelo.
Consome a estrutura de fechar_orcamento e usa o timbrado versionado.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.docx.formatos import brl, data_extenso

TIMBRADO_PATH = Path(__file__).resolve().parent / "timbrado" / "TIMBRADO_FLYINGSTUDIO.docx"

FONTE = "Calibri"
COR_TEXTO = RGBColor(0x1F, 0x23, 0x30)

ROTULOS_CATEGORIA = {
    "externas": "Ilustrações Externas",
    "internas": "Ilustrações Internas",
    "plantas": "Plantas Humanizadas 2D",
}

Seg = tuple[str, str]  # (texto, estilo)

APRESENTACAO: list[list[Seg]] = [
    [("Nascemos para dar forma ao invisível - ", "b"),
     ("Em 9 de maio de 2011, abrimos nossas portas com uma crença simples e poderosa: ", ""),
     ("“uma imagem vale mais do que mil palavras”", "iu"),
     (". Hoje, somos a ponte entre a ideia e a venda, provamos que a nossa arte não é "
      "apenas ilustrar a realidade, mas fazer o cliente vivenciar o futuro.", "")],
    [("Muito além das perspectivas - ", "b"),
     ("Esse sempre foi o nosso lema e, secretamente, a nossa profecia. Ao longo de quase "
      "duas décadas, acompanhamos o nascimento de centenas de empreendimentos e entendemos "
      "o que faz um projeto vender, o que atrai o olhar do investidor, o que acelera um "
      "lançamento e o que transforma um terreno em um verdadeiro case de sucesso e desejo.", "")],
    [("Nossa evolução foi um despertar", "b"),
     (" - A arte sempre será o nosso compasso, mas toda essa trajetória nos trouxe algo "
      "ainda mais valioso: a precisão mercadológica. Percebemos que uma imagem impecável é "
      "o convite perfeito, mas o nosso objetivo tornou-se assumir o controle de toda a "
      "experiência de compra. Nós não apenas ilustramos o amanhã; nós fazemos com que ele "
      "seja vivenciado. Para tangibilizar o amanhã, desenhamos um universo onde a "
      "tecnologia une encantamento e estratégia. A gestão fluida dos nossos aplicativos "
      "garante o controle absoluto da apresentação, preparando o terreno para o nosso "
      "D.sbrave, uma poderosa ferramenta de imersão que permite ao cliente caminhar e já "
      "projetar a sua vida no futuro lar, explorando cada detalhe em 360º. E nós fomos "
      "além: através da Realidade Aumentada, materializamos o projeto direto na mesa de "
      "negociação, enquanto nossas Salas Imersivas transformam o estande de vendas em um "
      "verdadeiro portal sensorial, arrebatando o cliente no momento decisivo da compra. "
      "Somamos tudo isso a grandiosidade dos nossos filmes cinematográficos e conceituais, "
      "que conectam metros quadrados a narrativas reais de vida. O visual atrai, mas é a "
      "imersão completa que fecha a venda.", "")],
]

SOLICITACOES: list[list[Seg]] = [
    [("Arquitetura: ", "b"),
     ("• Plantas • Elevação da Fachada • Estudo de Cores da Fachada • Cortes;", "")],
    [("Paisagismo: ", "b"),
     ("• Implantação • Detalhamentos• Especificação de Revestimentos • Estudo de Vegetação "
      "com Especificação de Espécies • Referências do Mobiliário;", "")],
    [("Decoração: ", "b"),
     ("• Plantas com Layout • Desenhos de Pisos • Elevações de Paredes • Especificações de "
      "materiais • Projeto de Forro e Iluminação • Descrição ou book de mobiliários.", "")],
]

OBS_SOLICITACOES: list[Seg] = [
    ("OBS: Na ausência de qualquer um dos itens necessários ao desenvolvimento do projeto, "
     "a ", ""),
    ("NID Studio", "b"),
    (" poderá ser consultada para propor soluções de conceito, layout, ambientação, "
     "fachada, materiais, mobiliário, decoração ou PDV, conforme a necessidade "
     "identificada, por meio de um escopo complementar a ser avaliado e apresentado à "
     "parte.", ""),
]

CONSIDERACOES: list[list[Seg]] = [
    [("Etapas e Tiros de Aprovação:", "b"),
     (" Esta proposta contempla o envio inicial do tiro de ", ""),
     ("Shade", "i"),
     (", seguido do tiro de apresentação denominado ", ""),
     ("“R00”", "b"),
     (". Estão inclusas no escopo 03 (três) rodadas de revisões, denominadas ", ""),
     ("“R01”", "b"), (", ", ""), ("“R02”", "b"), (" e ", ""), ("“R03”", "b"),
     (", culminando na entrega final denominada ", ""),
     ("“HR”", "b"),
     (" (High Resolution).", "")],
    [("Ajustes Finos e Adicionais:", "b"),
     (" Damos ênfase que, a partir do tiro ", ""),
     ("“R00”", "b"),
     (", as rodadas seguintes consistem exclusivamente em ajustes finos. A partir de um "
      "eventual quarto tiro de apresentação (denominado ", ""),
     ("“R04”", "b"),
     ("), será cobrado um adicional de 25% do valor da imagem por tiro extra solicitado.", "")],
    [("Plataforma Oficial de Revisão:", "b"),
     (" Para garantir a organização, a agilidade e a precisão técnica das refações, todo o "
      "processo de feedback, comentários e aprovações (tanto dos filmes quanto das imagens "
      "3D) será realizado exclusivamente através do software especializado ", ""),
     ("Frame.io/Adobe.", "b")],
    [("Mecânica de Apontamentos:", "b"),
     (" A Contratada fornecerá à Contratante um link de acesso seguro à plataforma. "
      "Através do ", ""),
     ("Frame.io/Adobe", "b"),
     (", o cliente poderá inserir comentários, desenhar marcações, anexar informações "
      "(pdf, foto, dwg, etc) e solicitar ajustes exatamente no frame do vídeo ou no ponto "
      "específico da imagem estática que deseja alterar, eliminando ruídos de comunicação. ", ""),
     ("“Para garantir agilidade e facilitar o processo de adaptação, sugerimos a "
      "visualização do guia prático em vídeo de como realizar revisões dentro da "
      "plataforma.”", "iu")],
    [("Alterações de Projeto:", "b"),
     (" Quaisquer alterações nos projetos originais (sejam de design de interiores, "
      "arquitetônico ou paisagismo) fornecidos inicialmente implicam em cobranças extras "
      "de modelagem, que serão orçadas e aprovadas em comum acordo.", "")],
    [("Refação e Remodelagem:", "b"),
     (" No decorrer das rodadas de tiros, havendo mudanças significativas no projeto que "
      "resultem na perda de até 50% da imagem já construída (sendo necessária a "
      "remodelagem ou retrocesso na etapa de produção), o trabalho será considerado e "
      "cobrado como uma imagem nova.", "")],
    [("Paralisação do Projeto:", "b"),
     (" Em caso de paralisação total ou parcial do escopo por um período de até 60 "
      "(sessenta) dias, deverá ser feito o acerto financeiro imediato das etapas já "
      "executadas. Para este cálculo de acerto, considera-se que cada tiro enviado após a "
      "aprovação do R00 corresponde a 25% do valor total da imagem.", "")],
    [("Cancelamento:", "b"),
     (" Em caso de descontinuidade e cancelamento do produto ou lançamento por qualquer "
      "motivo por parte da Contratante, considera-se justa e devida a quitação integral do "
      "saldo previsto nesta proposta.", "")],
    [("Direitos de Uso:", "b"),
     (" A Contratada cede à Contratante os direitos de uso das imagens produzidas para uso "
      "promocional em todo o seu material publicitário, única e exclusivamente vinculadas "
      "ao empreendimento contratado, não havendo débitos/atrasos financeiros.", "")],
]

ENTREGA_FINAL: list[list[Seg]] = [
    [("Formato e Envio:", "b"),
     (" Todo o material finalizado será enviado digitalmente via servidor FTP, link seguro "
      "para download ou cadastrados no ", ""),
     ("Frame.io/Adobe", "b"),
     (".", "")],
    [("Resolução das Imagens Estáticas:", "b"),
     (" As imagens finais (denominadas “HR”) serão entregues com ", ""),
     ("6000px em seu lado maior a 300dpi", "b"),
     (".", "")],
    [("Caso a Contratante necessite de imagens configuradas para impressões de até 1 (um) "
      "metro, a solicitação deve ser feita com antecedência à renderização final, sem "
      "custo adicional.", "")],
    [("Para imagens com medidas de impressão superiores a 1 (um) metro (como outdoors ou "
      "grandes painéis), favor consultar previamente os valores adicionais de render, com "
      "custo estimado de 20% do valor da imagem, consultar.", "")],
    [("Resolução das Animações/Filmes:", "b"),
     (" Os passeios virtuais e filmes integrados serão entregues finalizados no formato ", ""),
     ("Full HD a 30 FPS", "b"),
     (" ou propostas via ", ""),
     ("RINNO FILMS", "b"),
     (", consultar.", "")],
]

PARCELAS_PAGAMENTO = (
    (50, "Na aprovação desta Proposta"),
    (25, "Envio dos Shades"),
    (25, "Envio HR — Imagens finais"),
)


# ---------- helpers ----------


def _run(p, texto, *, estilo=""):
    r = p.add_run(texto)
    r.font.name = FONTE
    r.font.size = Pt(11)
    r.font.color.rgb = COR_TEXTO
    r.bold = "b" in estilo
    r.italic = "i" in estilo
    r.underline = "u" in estilo
    if "h" in estilo:
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
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
        _run(p, "FLYING studio", estilo="b")

    # ===== Cabeçalho da proposta (cliente/REF e A/C com marca-texto, como no modelo) =====
    p = _par(doc, depois=2)
    _run(p, "PROPOSTA DE IMAGENS, FILMES E TECNOLOGIAS 3D", estilo="b")
    p = _par(doc, depois=2)
    _run(p, f"{cliente['empresa'].upper()} - REF: {cliente['ref'].upper()}", estilo="bh")
    p = _par(doc, depois=10)
    _run(p, f"A/C: {cliente['contato'].upper()}", estilo="bh")

    # ===== 1 – Apresentação =====
    _titulo_secao(doc, "1", "APRESENTAÇÃO FLYING STUDIO")
    for segs in APRESENTACAO:
        p = _par(doc, depois=8, justificado=True)
        _rich(p, segs)

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
            _run(p, texto)
        p = _par(doc, antes=6, depois=8)
        _run(p, f"Valor total: {brl(bloco['total'])}", estilo="b")

    sub += 1
    _subtitulo(doc, f"2.{sub} INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA DESCRITOS:")
    p = _par(doc, depois=2, recuo=1.25)
    _run(p, brl(fin["total"]).replace("R$", "R$ "))
    if fin["desconto_pct"] > 0:
        rotulo = fin["rotulo"] or f"{fin['desconto_pct']}%"
        p = _par(doc, depois=8, recuo=1.25)
        _run(p, f"(Valor bruto: {brl(fin['subtotal'])}  ·  Desconto ({rotulo}): "
                f"-{brl(fin['desconto_valor'])})", estilo="i")

    sub += 1
    _subtitulo(doc, f"2.{sub} FORMA DE PAGAMENTO:")
    for pct, marco in PARCELAS_PAGAMENTO:
        v = fin["total"] * (pct / 100.0)
        p = _par(doc, depois=2, recuo=1.25)
        _run(p, f"{pct}% – {marco} ({brl(v)})")

    # ===== 3 – Prazos / Solicitações / Considerações / Entregas =====
    _titulo_secao(doc, "3", "PRAZOS / SOLICITAÇÕES / CONSIDERAÇÕES / ENTREGAS")

    p = _par(doc, depois=2, recuo=1.0)
    _run(p, "3.1 Shades", estilo="b")
    _run(p, " – 20 (Vinte) dias")
    p = _par(doc, depois=2, recuo=1.0)
    _run(p, "1º Tiro", estilo="b")
    _run(p, " – 15 (Quinze) dias após a aprovação dos Shades,")
    p = _par(doc, depois=8, recuo=1.0)
    _run(p, "Revisões", estilo="b")
    _run(p, " – 10 (Dez) dias para contemplar e enviar novos tiros.")

    p = _par(doc, antes=8, depois=6)
    _run(p, "3.2 SOLICITAÇÕES: Arquivos e definições necessários à execução do serviço.",
         estilo="b")
    for segs in SOLICITACOES:
        p = _par(doc, depois=2, recuo=1.0, justificado=True)
        _rich(p, segs)
    p = _par(doc, antes=6, depois=8, recuo=1.0, justificado=True)
    _rich(p, OBS_SOLICITACOES)

    _subtitulo(doc, "3.3 CONSIDERAÇÕES IMAGENS:")
    for segs in CONSIDERACOES:
        _bullet(doc, segs)

    _subtitulo(doc, "3.4 ENTREGA FINAL:")
    for segs in ENTREGA_FINAL:
        _bullet(doc, segs)

    # ===== Assinatura =====
    p = _par(doc, antes=16, depois=12)
    _run(p, f"São Paulo, {data_extenso(data)}.")
    p = _par(doc, depois=24)
    _run(p, "De acordo,")
    # Linha de assinatura VAZIA — o cliente assina sobre ela no PDF enviado.
    p = _par(doc, depois=0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "_" * 60)

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida
