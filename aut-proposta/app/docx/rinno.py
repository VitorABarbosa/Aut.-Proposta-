"""Corpo da proposta da Rinno Films — filmes e tecnologias 3D.

Estrutura própria, diferente da Flying: cada filme traz o seu escopo em
bullets logo abaixo do item ("Este item inclui:"), o investimento e a forma de
pagamento ficam numa seção 3 separada, e a seção 4 cobre cronograma por
semana, considerações e direito de uso.

O escopo de cada filme é casado pelo começo da descrição do catálogo
(`ESCOPO_POR_FILME`) — item sem escopo cadastrado sai só com a linha do item,
nunca com o escopo de outro.
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
    valor_do_item,
)
from app.docx.formatos import brl
from app.dominio.texto import normalizar
from app.empresas import Empresa

APRESENTACAO: list[list[Seg]] = [
    [("O futuro não aceita mais o comum. ", "b"),
     ("O mercado imobiliário foi, por muito tempo, definido por estruturas, metragens e "
      "promessas padronizadas. Nós nascemos para romper essa inércia. O nosso compromisso "
      "é com a narrativa, moldando a emoção para entregar filmes com a essência puramente "
      "cinematográfica.", "")],
    [("Para nós, um novo empreendimento nunca é apenas uma estrutura a ser erguida. Ele é "
      "um universo de detalhes minuciosos, de emoções latentes e desafios superados que "
      "clamam para ser contados. Nós olhamos para o horizonte e vemos roteiros vivos, "
      "pulsando. Unimos essa sensibilidade profunda à técnica para entregar um padrão "
      "cinematográfico que redefine, de uma vez por todas, a nova era narrativa. É aqui "
      "que nasce o ", ""),
     ("cinema imobiliário", "b"), (".", "")],
    [("Nesse novo cinema, a conexão desperta antes do concreto. Nós orquestramos a emoção, "
      "revelando sempre o “porquê” antes do “o quê”. A alma do empreendimento ganha vida em "
      "documentários que eternizam a primeira centelha criativa. A arquitetura se eleva à "
      "arte em filmes conceituais e de produto que despertam o desejo absoluto. E, para que "
      "a marca pulse intensamente, aplicamos engenharia de atenção em narrativas virais que "
      "dominam as redes sociais e ditam as conversas.", "")],
    [("Ainda assim, no centro de tanta vanguarda estética, uma verdade profundamente humana "
      "guia os nossos roteiros: para muitos, esta não é uma transação. É a conquista de uma "
      "vida. O suor materializado. O primeiro e, tantas vezes, o único imóvel. Nós "
      "entendemos a grandeza dessa realização. A técnica, por si só, é fria e vazia. É por "
      "isso que, em cada frame capturado, em cada movimento de câmera e no compasso de cada "
      "trilha sonora, nós colocamos coração, alma e sentimento. O mercado imobiliário não "
      "será apenas visto. Ele será sentido, desejado e eternizado.", "")],
    [("Nós somos a nova era narrativa. Nós somos o cinema imobiliário.", "b")],
]

# Escopo por tipo de filme, casado pelo começo da descrição do catálogo.
ESCOPO_POR_FILME: dict[str, list[list[Seg]]] = {
    "Filme Conceito": [
        [("Estrutura:", "b"), (" Localização, Conceito e Produto.", "")],
        [("Roteiro:", "b"),
         (" Roteiro Cliente, ou Rinno Pauta de acordo com Book/Folder do produto fornecido "
          "pela agência de publicidade.", "")],
        [("Pós-Produção:", "b"), (" Edição e composição.", "")],
        [("Conteúdo Adicional:", "b"),
         (" Takes animados para redes sociais e mobile (versão 7 segundos cada).", "")],
        [("Áudio:", "b"), (" Personalização de trilha sonora + locução, se for necessário.", "")],
        [("Recursos:", "b"), (" Banco de Imagens de humanização e respiros.", "")],
        [("Efeitos:", "b"), (" Overlay texto e efeitos especiais.", "")],
    ],
    # Como saiu para a Turtitta (set/2026): sem linha de "Estrutura".
    "Filme Institucional": [
        [("Roteiro:", "b"),
         (" Roteiro Cliente, ou Rinno Pauta de acordo com Book/Folder do produto fornecido "
          "pela agência de publicidade.", "")],
        [("Pós-Produção:", "b"), (" Edição e composição.", "")],
        [("Áudio:", "b"), (" Personalização de trilha sonora + locução, se for necessário.", "")],
        [("Recursos:", "b"), (" Banco de Imagens de humanização e respiros.", "")],
        [("Efeitos:", "b"), (" Overlay texto e efeitos especiais.", "")],
    ],
    "Filme Corretor / Produto": [
        [("Estrutura:", "b"), (" Filme corretor.", "")],
        [("Roteiro:", "b"),
         (" Roteiro Cliente, ou Rinno Pauta de acordo com Book/Folder do produto fornecido "
          "pela agência de publicidade.", "")],
        [("Pós-Produção:", "b"), (" Edição e composição.", "")],
        [("Áudio:", "b"), (" Personalização de trilha sonora, podendo ter locução.", "")],
        [("Recursos:", "b"), (" Banco de Imagens de humanização e respiros.", "")],
        [("Efeitos:", "b"), (" Overlay texto e efeitos especiais.", "")],
    ],
    "Filme Viral": [
        [("Conteúdo:", "b"),
         (" Um filme para redes sociais de até 1:00 (um minuto), formato 9:16.", "")],
    ],
    "Filme Documentário": [
        [("Estrutura:", "b"), (" Documentário — um episódio de até 1:00 (um minuto).", "")],
        [("Roteiro:", "b"), (" Pauta Rinno a partir do material e das entrevistas cedidas.", "")],
        [("Pós-Produção:", "b"), (" Edição, composição e finalização de cor.", "")],
        [("Áudio:", "b"), (" Personalização de trilha sonora, podendo ter locução.", "")],
    ],
}

CONSIDERACOES: list[list[Seg]] = [
    [("Diretrizes e Briefing:", "b"),
     (" O filme será desenvolvido com base no briefing/folder do produto fornecido pela "
      "Contratante ou agência de marketing.", "")],
    [("Fornecimento de Acervo Técnico:", "b"),
     (" Para início dos trabalhos, a Contratante enviará todas as informações de "
      "identidade, folder e logos do produto.", "")],
    [("Etapas de Aprovação:", "b"),
     (" A produção do filme seguirá um fluxo estruturado: 1ª Etapa — Roteiro (escrito) "
      "desenvolvido e aprovado junto à Contratante/Agência; 2ª Etapa — Apresentação do "
      "Preview em vídeo digital para avaliação da narrativa; 3ª Etapa — Renderização e "
      "Pós-produção (Color Grading, Mixagem de Som, Motion Graphics).", "")],
    [("Observação:", "b"),
     (" A etapa de renderização e pós-produção só é possível após a aprovação das imagens "
      "digitais estáticas (perspectivas) exibidas no filme. Após a aprovação formal, "
      "fecharemos em versão final e em alta resolução.", "")],
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
      "específico da imagem estática que deseja alterar, eliminando ruídos de comunicação.", "")],
]

ENTREGA_E_DIREITOS: list[list[Seg]] = [
    [("Formato de Entrega:", "b"),
     (" Os filmes finais serão entregues em formato digital de alta compatibilidade "
      "(.MP4 ou .MOV, codec H.264/H.265) em resolução ", ""),
     ("Full HD a 30 FPS", "b"),
     (", via Frame.io/Adobe ou link de download na nuvem (FTP, Google Drive, etc.).", "")],
    [("Direitos de Exibição:", "b"),
     (" A Contratada cede à Contratante os direitos patrimoniais de uso dos filmes para "
      "uso promocional única e exclusivamente do empreendimento contratado.", "")],
    [("Integridade da Obra:", "b"),
     (" A Contratante não poderá modificar nem ceder o filme a terceiros sem consentimento "
      "e aviso prévio por escrito da Contratada.", "")],
    [("Política de Cancelamento (Pré-Produção):", "b"),
     (" Caso a Contratante decida suspender os serviços antes do início da primeira etapa "
      "(Preview), a Contratada irá avaliar os custos operacionais incorridos até o momento "
      "e repassá-los à Contratante.", "")],
    [("Política de Cancelamento (Pós-Produção):", "b"),
     (" Após a primeira etapa concluída (Preview), o projeto será cobrado integralmente, "
      "independentemente de rescisão do contrato pela Contratante.", "")],
    [("Upsell de Resolução (Opcional):", "b"),
     (" Os valores desta proposta contemplam a entrega dos filmes em Full HD. Caso "
      "precisem do filme masterizado em resolução 4K (Ultra HD), o mesmo terá um acréscimo "
      "de 25% no valor total do orçamento.", "")],
    [("Arquivos-fonte:", "b"),
     (" Os arquivos utilizados para a produção, incluindo modelos 2D e 3D, cenas, texturas, "
      "materiais, arquivos de renderização e demais arquivos editáveis, tanto para produção "
      "das imagens quanto para filmes permanecem de propriedade única e exclusiva do ", ""),
     ("Grupo Flying", "b"),
     (" e não integram a entrega desta proposta. A contratação contempla exclusivamente os "
      "materiais finais especificados no escopo, para o uso exclusivo do lançamento "
      "pertinente à contratação.", "")],
]

CRONOGRAMA: list[list[Seg]] = [
    [("Semana 1:", "b"),
     (" Roteiro, após o R01 das imagens: briefing e envio de materiais da agência "
      "(folder do produto).", "")],
    [("Semanas 2 e 3:", "b"),
     (" Renderização, captação e primeira montagem (Preview) e envio para aprovação.", "")],
    [("Semana 4:", "b"),
     (" Ajustes finais, cor, áudio e entrega final — etapa sempre pendente das entregas "
      "das imagens em HR.", "")],
]

# 50/50 é o que está no modelo oficial da Rinno e nas propostas enviadas
# (Turtitta, Unicos); o 50/25/25 da planilha é o padrão da Flying.
PARCELAS_PAGAMENTO = (
    (50, "Na aprovação desta Proposta"),
    (50, "Na Entrega dos Filmes"),
)


def _escopo_de(descricao: str) -> list[list[Seg]]:
    """Casa pelo começo da descrição sem ligar para maiúscula ou acento:
    "Filme institucional de até 2:00", escrito pelo usuário, é institucional."""
    alvo = normalizar(descricao)
    for prefixo, bullets in ESCOPO_POR_FILME.items():
        if alvo.startswith(normalizar(prefixo)):
            return bullets
    return []


def escrever(doc, empresa: Empresa, cliente: dict[str, str], fechado: dict[str, Any],
             data: dt.date) -> None:
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]

    cabecalho_proposta(doc, empresa, cliente)

    # ===== 1 – Apresentação =====
    _titulo_secao(doc, "1", "APRESENTAÇÃO RINNO FILMS: NASCE O CINEMA IMOBILIÁRIO.")
    for segs in APRESENTACAO:
        p = _par(doc, depois=8, justificado=True)
        _rich(p, segs)

    # ===== 2 – Itens, cada um com o seu escopo =====
    _titulo_secao(doc, "2", "ITENS A SEREM DESENVOLVIDOS:")

    sub = 0
    for _cat, rotulo, bloco in itens_orcados(orc):
        for item in bloco["itens"]:
            sub += 1
            # No modelo oficial o item é "Um Filme Conceito de até 2:30…".
            desc = item["descricao"]
            artigo = "Um " if normalizar(desc).startswith("filme") else ""
            # O valor de cada item sai SEMPRE. A proposta que só mostra o
            # total da categoria obriga o cliente a perguntar quanto custa
            # cada filme — e a resposta some do documento enviado.
            _subtitulo(doc, f"2.{sub} {artigo}{desc} — {valor_do_item(item['preco'])}")
            escopo = _escopo_de(desc)
            # "Este item inclui:" só quando há lista; o viral tem uma linha só
            # ("Conteúdo: …") e no modelo ela vem direto.
            if len(escopo) > 1:
                p = _par(doc, depois=4, recuo=1.0)
                _run(p, "Este item inclui:", estilo="b")
            for segs in escopo:
                _bullet(doc, segs)
        p = _par(doc, antes=6, depois=8)
        _run(p, f"{rotulo} — Valor total: {brl(bloco['total'])}", estilo="b")

    # ===== 3 – Investimento + forma de pagamento =====
    _titulo_secao(doc, "3", "INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA "
                            "DESCRITOS + FORMA DE PAGAMENTO:")
    bloco_investimento(doc, "3.1", fin,
                       titulo="Investimentos da Produção Técnica dos Filmes Acima")
    bloco_pagamento(doc, "3.2", fin, PARCELAS_PAGAMENTO)

    # ===== 4 – Prazos, considerações e entrega =====
    _titulo_secao(doc, "4", "PRAZOS / CRONOGRAMAS:")
    for segs in CRONOGRAMA:
        p = _par(doc, depois=2, recuo=1.0, justificado=True)
        _rich(p, segs)
    p = _par(doc, antes=6, depois=8, recuo=1.0, justificado=True)
    _run(p, "OBS: ", estilo="b")
    _run(p, "os prazos começam a contar a partir da obtenção das aprovações necessárias e "
            "da conclusão das imagens em alta resolução (HR).")

    _subtitulo(doc, "4.1 CONSIDERAÇÕES DO PROJETO:")
    for segs in CONSIDERACOES:
        _bullet(doc, segs)

    _subtitulo(doc, "4.2 ENTREGA E DIREITO DE USO:")
    for segs in ENTREGA_E_DIREITOS:
        _bullet(doc, segs)

    assinatura(doc, data)
