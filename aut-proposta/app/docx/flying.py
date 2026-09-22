"""Corpo da proposta da Flying Studio — imagens, filmes e tecnologias 3D.

Fidelidade run a run ao modelo oficial (PROPOSTA_EXEMPLO): estrutura numerada,
textos exatos e os destaques inline (negritos em "R00"/"HR"/Frame.io/NID
Studio, itálicos e sublinhados). Os campos do cliente saem em negrito, sem
marca-texto.

Três seções: 1 apresentação, 2 itens + investimento + pagamento, 3 prazos /
solicitações / considerações / entrega.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from app.docx.base import (
    Seg,
    _bullet,
    _par,
    _rich,
    _run,
    _subtitulo,
    _titulo_secao,
    assinatura,
    bloco_investimento,
    bloco_pagamento,
    cabecalho_proposta,
    itens_orcados,
)
from app.docx.formatos import brl
from app.dominio.orcamento import e_categoria_por_ambiente
from app.dominio.texto import normalizar
from app.empresas import Empresa

# Escopo padrão de cada serviço, como sai nas propostas enviadas: o item é uma
# linha e, abaixo dele, o que está incluído, numerado. Vale para os serviços
# que têm escopo fechado (tecnologia, tour, maquete); imagem não tem — cada
# cena é uma cena.
#
# Casado pelo começo da descrição do catálogo, como na Rinno. Serviço sem
# escopo cadastrado aqui sai só com a linha do item — nunca com o escopo de
# outro. Faltam os textos oficiais de vários serviços; quando chegarem, entram
# aqui e aparecem na proposta sem mexer em mais nada.
ESCOPO_POR_ITEM: dict[str, list[str]] = {
    "desenvolvimento de aplicacao web": [
        "Catálogo Digital Interativo, permitindo ao usuário uma experiência ao interagir "
        "na tela touch screen",
        "Apresentação do Empreendimento",
        "Informações Institucional",
        "Implantação",
        "Perspectivas / Imagens",
        "Localização Empreendimento – 360º PINS",
        "Vídeos Conceito + Produto + Redes Sociais",
        "Revista Digital",
    ],
    "tour virtual": [
        "Elaboração 3d (Arquitetura / Decoração)",
        "Render 360° VR",
        "Versão Mobile Offline – Panos 360º",
    ],
    # Flying_Dsbrave_Ousy_AnexoI_R00: o D.sbrave é uma plataforma, e o escopo
    # são os módulos dela. Na proposta da Ousy saiu fechado em R$ 69.000; na da
    # Elecon só a parte de apartamento modelo virtual, por ambiente.
    "d.sbrave": [
        "Visita Virtual do Apto",
        "Visita Virtual Áreas de Lazer",
        "Simulação de Insolação",
        "Maquete Eletrônica Virtual",
        "Revista Digital",
        "Split.View / Acompanhamento de Obra",
        "Espelho de Vendas (integração com CV)",
    ],
    "maquete eletronica": [
        "Simulação de Insolação",
        "360° View",
        "Marcadores de tipologia",
    ],
}


def _escopo_de(descricao: str) -> list[str]:
    """Casa pelo começo da descrição, sem ligar para acento ou maiúscula."""
    alvo = normalizar(descricao)
    for prefixo, linhas in ESCOPO_POR_ITEM.items():
        if alvo.startswith(prefixo):
            return linhas
    return []

# Categorias fixas de antes do catálogo dinâmico — fallback de leitura para
# orçamento salvo sem `_categorias`.
ROTULOS_CATEGORIA = {
    "externas": "Ilustrações Externas",
    "internas": "Ilustrações Internas",
    "plantas": "Plantas Humanizadas 2D",
}

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


def escrever(doc, empresa: Empresa, cliente: dict[str, str], fechado: dict[str, Any],
             data: dt.date) -> None:
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]
    ambientes = int(orc.get("ambientes") or 1)

    cabecalho_proposta(doc, empresa, cliente)

    # ===== 1 – Apresentação =====
    _titulo_secao(doc, "1", "APRESENTAÇÃO FLYING STUDIO")
    for segs in APRESENTACAO:
        p = _par(doc, depois=8, justificado=True)
        _rich(p, segs)

    # ===== 2 – Itens / Investimentos =====
    _titulo_secao(doc, "2", "ITENS A SEREM DESENVOLVIDOS / INVESTIMENTOS:")

    categorias = itens_orcados(orc)
    if not orc.get("_categorias"):
        categorias = [(cat, ROTULOS_CATEGORIA[cat], orc[cat])
                      for cat in ("externas", "internas", "plantas")
                      if orc.get(cat) and orc[cat]["qtd"]]

    sub = 0
    for cat, rotulo, bloco in categorias:
        sub += 1
        # Serviço cobrado por ambiente traz a quantidade no título, como nas
        # propostas enviadas: "Vista Virtual Web – Áreas de Lazer (7 ambientes)".
        titulo = rotulo
        if e_categoria_por_ambiente(cat) and ambientes > 1:
            titulo = f"{rotulo} ({ambientes} ambientes)"
        _subtitulo(doc, f"2.{sub} {titulo}")
        for idx, item in enumerate(bloco["itens"], start=1):
            p = _par(doc, depois=2, recuo=1.25)
            _run(p, f"{idx}. {item['descricao']} — {brl(item['preco'])}")
            for linha in _escopo_de(item["descricao"]):
                sub_p = _par(doc, depois=0, recuo=2.0)
                _run(sub_p, f"– {linha}")
        p = _par(doc, antes=6, depois=8)
        _run(p, f"Valor total: {brl(bloco['total'])}", estilo="b")

    sub += 1
    bloco_investimento(doc, f"2.{sub}", fin)
    sub += 1
    bloco_pagamento(doc, f"2.{sub}", fin, PARCELAS_PAGAMENTO)

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

    assinatura(doc, data)
