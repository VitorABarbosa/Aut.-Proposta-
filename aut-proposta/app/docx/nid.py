"""Corpo da proposta da NID Studio — projeto de interiores, fachada e PDV.

A mais diferente das três: o produto não é imagem, é projeto, e por isso o
documento tem seis seções — apresentação, escopo contratado, entregáveis por
fase (EP / PRE / EX, com as lâminas numeradas), cronograma, investimento e as
considerações gerais de responsabilidade.

Duas correções em relação ao modelo em Word de onde este corpo foi tirado, por
serem contradições dentro do próprio documento:
- a hora técnica aparecia como R$ 600,00 no investimento e R$ 300,00/h nas
  considerações; aqui o valor é definido uma vez, no item 5.3, e a
  consideração 6.3 remete a ele em vez de repetir outro número;
- a taxa de acompanhamento era citada como "prevista no Item 4", mas está no
  item 5.
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
from app.empresas import Empresa

HORA_TECNICA = 600.0
TAXA_ACOMPANHAMENTO_PCT = 10

APRESENTACAO: list[list[Seg]] = [
    [("Quem Somos: O Seu Ninho Criativo. ", "b"),
     ("Na NID STUDIO, entendemos o conceito de lar como um ninho: um espaço de aconchego, "
      "segurança e personalidade. Somos um estúdio criativo dedicado a transformar "
      "ambientes em verdadeiros refúgios que acolhem, inspiram e refletem a essência do "
      "cliente e do lançamento. Nosso trabalho vai além da estética; buscamos criar "
      "espaços funcionais, confortáveis e cheios de significado, como um verdadeiro ninho "
      "que abraça quem nele habita.", "")],
    [("O Que Fazemos. ", "b"),
     ("Na NID STUDIO, desenvolvemos produtos que transcendem a estética e convidam a uma "
      "experiência sensorial única. Nosso escopo de atuação inclui o conceito de produto, "
      "design de interiores das áreas comuns e apartamento modelo, assim como design de "
      "fachadas, além de projetos de plantão de venda (PDV) e a entrega, consultoria e "
      "montagem das áreas comuns. Criamos lugares que não apenas habitamos, mas sentimos, "
      "vivemos e lembramos — espaços verdadeiramente inesquecíveis e únicos, um refúgio "
      "onde a criatividade acolhe e transforma.", "")],
    [("Metodologia NID e Nossos Diferenciais. ", "b"),
     ("O verdadeiro diferencial da NID Studio está na nossa ", ""),
     ("análise consultiva de inteligência arquitetônica", "i"),
     (": uma abordagem aprofundada e estratégica que avalia com precisão as dinâmicas do "
      "mercado imobiliário. Essa análise rigorosa é sustentada por nossos pilares de "
      "processo e diferenciais, focados em unir alta excelência em design e usabilidade. "
      "Cada projeto é guiado por empatia e inteligência, pensando no uso, na "
      "funcionalidade e na experiência sensorial que os espaços podem oferecer. Para o "
      "mercado imobiliário, isso se traduz em plantões de vendas magnéticos, de alta "
      "atração, e áreas comuns que materializam o desejo de compra, elevando o valor "
      "percebido de todo o empreendimento.", "")],
]

FASES: list[tuple[str, str, str, list[str]]] = [
    ("3.1", "Estudo Preliminar (EP)",
     "Fase de inteligência, concepção estética e definição de fluxos. O objetivo é "
     "aprovar o conceito arquitetônico e o layout funcional.",
     ["Lâmina 01: Análise Consultiva e Moodboard",
      "Lâmina 02: Planta de Layout — Fluxo e Experiência",
      "Lâmina 03: Estudo Volumétrico / Imagens 3D Preliminares (proibido uso publicitário)"]),
    ("3.2", "Projeto Pré-Executivo (PRE)",
     "Fase de aprofundamento técnico e definições prévias para orçamentação macro.",
     ["Lâmina 04: Planta Baixa Técnica",
      "Lâmina 05: Elevações Principais",
      "Lâmina 06: Planta de Indicação de Acabamentos"]),
    ("3.3", "Projeto Executivo (EX)",
     "Fase de detalhamento técnico minucioso para envio à obra, empreiteiros e fornecedores.",
     ["Lâmina 07: Planta de Construir e Demolir",
      "Lâmina 08: Planta de Forro e Luminotécnica",
      "Lâmina 09: Planta de Pontos Elétricos e Hidráulicos",
      "Lâmina 10: Planta de Paginação de Pisos e Revestimentos",
      "Lâmina 11: Detalhamento de Marcenaria",
      "Lâmina 12: Detalhamento de Marmoraria e Bancadas",
      "Lâmina 13: Caderno de Especificações Final"]),
]

CRONOGRAMA: list[list[Seg]] = [
    [("Estudo Preliminar (EP):", "b"), (" 15 (Quinze) dias úteis.", "")],
    [("Projeto Pré-Executivo (PRE):", "b"),
     (" 10 (Dez) dias úteis, contados a partir da aprovação do EP.", "")],
    [("Projeto Executivo (EX):", "b"),
     (" 15 (Quinze) dias úteis, contados a partir da aprovação do PRE.", "")],
    [("Revisões:", "b"),
     (" estão contempladas até 03 (três) rodadas de revisão na fase de Estudo Preliminar, "
      "com prazo de devolutiva de até 07 (sete) dias úteis. Os prazos passam a contar "
      "exclusivamente após o recebimento de todas as informações, plantas base (DWG) e o "
      "aceite formal desta proposta.", "")],
]

CONSIDERACOES: list[list[Seg]] = [
    [("6.1 Entrega Final e Disponibilização de Arquivos:", "b"),
     (" Todo o material finalizado referente ao Projeto Executivo será entregue "
      "digitalmente, nos formatos PDF e DWG, via plataforma FTP indicada pela Contratante "
      "(Autodoc ou similar) ou link seguro para download. Após o upload da revisão final "
      "na plataforma designada, o projeto é considerado concluído. Impressões físicas ou "
      "plotagens, caso solicitadas, serão orçadas e cobradas à parte.", "")],
    [("6.2 Projetos Complementares e Compatibilização:", "b"),
     (" O escopo da NID Studio abrange exclusivamente o Projeto de Arquitetura de "
      "Interiores e Cenografia do PDV. A Contratante fica responsável pela contratação, "
      "execução e aprovação legal de todos os projetos complementares necessários "
      "(estrutural, fundações, elétrica, hidrossanitária, AVAC, prevenção de incêndio "
      "etc.). O fornecimento das plantas de pontos elétricos e hidráulicos (Lâmina 09) "
      "serve como guia conceitual arquitetônico para que as engenharias específicas "
      "desenvolvam seus projetos executivos.", "")],
    [("6.3 Alterações Decorrentes do Empreendimento:", "b"),
     (" O projeto de interiores é baseado na arquitetura legal/base (DWG) fornecida no "
      "início dos trabalhos. Caso ocorram alterações posteriores por parte da "
      "incorporadora, da construtora ou dos projetistas de complementares (mudança em "
      "prumadas, rebaixos de viga não previstos, shafts ou recuos estruturais) que "
      "obriguem o retrabalho do projeto de interiores das áreas comuns, as horas "
      "dedicadas a essa readequação serão contabilizadas e cobradas pela hora técnica "
      "prevista no item 5.3, mediante prévia aprovação de orçamento pela Contratante.", "")],
    [("6.4 Paralisação do Projeto:", "b"),
     (" Em caso de paralisação total ou parcial do escopo por parte da Contratante por "
      "período superior a 60 (sessenta) dias, deverá ser feito o acerto financeiro "
      "imediato proporcional às etapas executadas. O retorno às atividades estará sujeito "
      "à repactuação de cronograma e possíveis reajustes de valores.", "")],
    [("6.5 Cancelamento:", "b"),
     (" A descontinuidade do projeto por qualquer motivo por parte da Contratante "
      "acarretará a quitação integral das fases já iniciadas, bem como a retenção "
      "irrestrita do sinal financeiro pago (mobilização de equipe).", "")],
    [("6.6 Direitos Autorais, Exclusividade e Uso de Imagem:", "b"),
     (" A autoria intelectual dos projetos e designs desenvolvidos pertence única e "
      "exclusivamente à ", ""),
     ("NID STUDIO", "b"),
     (", sendo intransferível. Fica garantido o direito inalienável do escritório de "
      "assinar a criação (logomarca/créditos) em placas de obra do estande, painéis "
      "informativos, folders do produto, revistas, portais imobiliários e demais materiais "
      "de divulgação do lançamento. O projeto cedido é válido única e exclusivamente para "
      "execução no empreendimento e PDV especificados no cabeçalho, sendo proibida a "
      "replicação do design, marcenarias e soluções de fachada em outros estandes ou "
      "empreendimentos da Contratante sem a devida negociação de novos direitos autorais.", "")],
    [("6.7 Isenção de Responsabilidade sobre a Execução e Vícios Construtivos:", "b"),
     (" O escopo da NID Studio restringe-se à concepção e ao detalhamento do projeto de "
      "design. A contratação de mão de obra, compra de materiais, gestão de canteiro e a "
      "responsabilidade civil sobre a execução física do estande e dos interiores são de "
      "responsabilidade integral da construtora ou empreiteira contratada. A NID Studio "
      "não se responsabiliza por vícios construtivos, falhas de execução, atrasos da obra "
      "ou passivos trabalhistas.", "")],
    [("6.8 Imagens Fotorrealistas e Material de Marketing:", "b"),
     (" As modelagens e imagens 3D geradas durante as fases deste projeto possuem caráter "
      "exclusivamente técnico e de aprovação de design. Não estão inclusas neste escopo a "
      "produção de imagens, animações ou passeios virtuais (VR) em alta resolução para uso "
      "em campanhas de marketing, plantão de vendas ou encartes publicitários. Tais "
      "serviços de computação gráfica e tecnologia 3D poderão ser orçados à parte com a ", ""),
     ("Flying Studio", "b"), (".", "")],
    [("6.9 Prazos de Aprovação e Retorno da Contratante:", "b"),
     (" O cronograma prevê um fluxo contínuo de trabalho. A Contratante terá prazo de até "
      "05 (cinco) dias úteis para avaliar e/ou aprovar formalmente cada fase entregue. O "
      "tempo em que o projeto permanecer sob análise do cliente ou de suas engenharias não "
      "é computado no prazo de entrega do escritório. Atrasos no retorno das aprovações "
      "prorrogarão automaticamente os prazos das fases subsequentes na mesma proporção.", "")],
    [("6.10 Isenção por Erros de Execução ou Medidas In Loco:", "b"),
     (" A NID Studio desenvolve suas soluções técnica e dimensionalmente com base nas "
      "plantas fornecidas pela Contratante, e não assume responsabilidade civil ou "
      "financeira por divergências métricas entre o projeto base e a realidade física "
      "construída na obra. Caso erros de execução (paredes fora de esquadro, shafts fora "
      "da posição projetada) impactem o encaixe de marcenarias, marmorarias ou paginações "
      "de revestimentos, os custos de correção correrão integralmente por conta da "
      "Contratante.", "")],
    [("6.11 Taxas e Emolumentos (RRT / CAU):", "b"),
     (" A emissão do Registro de Responsabilidade Técnica (RRT) de projeto será realizada "
      "pela NID Studio. O valor das guias e taxas de emissão será repassado para pagamento "
      "direto pela Contratante, não estando embutido no valor dos honorários de projeto.", "")],
    [("6.12 Especificidades para Design de Fachada:", "b"),
     (" O desenvolvimento do Design de Fachada limita-se à concepção estética, "
      "volumétrica, indicação de materiais, paginação de revestimentos e conceito "
      "luminotécnico externo. Aprovações legais ficam sob total responsabilidade da "
      "Contratante e de seu arquiteto legalizador. Os cálculos estruturais para fixação de "
      "brises, peles de vidro ou painéis metálicos deverão ser realizados por engenharia "
      "especializada contratada pela incorporadora.", "")],
    [("6.13 Especificidades para Apartamento Modelo Decorado:", "b"),
     (" O projeto para Apartamento Modelo destina-se exclusivamente à unidade cenográfica "
      "do plantão de vendas. A curadoria, compra e posicionamento de objetos decorativos "
      "soltos, obras de arte e enxoval demandam verba de custeio própria da Contratante. "
      "Mesmo após a desmobilização do modelo, a NID Studio mantém os direitos autorais e "
      "de imagem para uso em seu portfólio institucional.", "")],
    [("6.14 Especificidades para Áreas Comuns do Empreendimento:", "b"),
     (" O escopo compreende o detalhamento executivo e a entrega do Caderno de "
      "Especificações Técnicas. A logística física de entrega, montagem de equipamentos e "
      "instalação no canteiro deverá seguir a gestão da construtora. Caso a incorporadora "
      "opte pela coordenação de implantação (turnkey) pela NID Studio, incidirá a Taxa de "
      "Acompanhamento prevista no item 5.3.", "")],
    [("6.15 Exclusividade Crítica por Tipologia de Escopo:", "b"),
     (" O design, o detalhamento de marcenarias e os conceitos espaciais desenvolvidos "
      "para esta proposta possuem caráter de exclusividade estrita para o endereço e o "
      "empreendimento descritos no cabeçalho. É proibida a replicação total ou parcial dos "
      "desenhos da NID Studio em outras torres, remanescentes ou futuros lançamentos da "
      "incorporadora sem a expressa autorização por escrito e o respectivo pagamento de "
      "novos direitos autorais.", "")],
]

PARCELAS_PAGAMENTO = (
    (50, "Na aprovação desta Proposta"),
    (25, "Aprovação do Estudo Preliminar (EP)"),
    (25, "Entrega do Projeto Executivo (EX)"),
)


def escrever(doc, empresa: Empresa, cliente: dict[str, str], fechado: dict[str, Any],
             data: dt.date, mostra_precos_individuais: bool = False) -> None:
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]

    cabecalho_proposta(doc, empresa, cliente)

    # ===== 1 – Apresentação =====
    _titulo_secao(doc, "1", "APRESENTAÇÃO NID STUDIO")
    for segs in APRESENTACAO:
        p = _par(doc, depois=8, justificado=True)
        _rich(p, segs)

    # ===== 2 – Escopo contratado =====
    _titulo_secao(doc, "2", "ITENS A SEREM EXECUTADOS")
    _subtitulo(doc, "2.1 Escopo Contratado:")
    for _cat, _rotulo, bloco in itens_orcados(orc):
        for item in bloco["itens"]:
            p = _par(doc, depois=2, recuo=1.0)
            texto = item["descricao"]
            if mostra_precos_individuais:
                texto += f" — {brl(item['preco'])}"
            _run(p, "•   ")
            _run(p, texto)

    # ===== 3 – Escopo do projeto e entregáveis =====
    _titulo_secao(doc, "3", "ESCOPO DO PROJETO E ENTREGÁVEIS")
    p = _par(doc, depois=8, justificado=True)
    _run(p, "O desenvolvimento do projeto será dividido em 3 (três) etapas fundamentais, "
            "alinhadas ao cronograma de lançamento. A transição para a etapa seguinte "
            "ocorrerá somente mediante aprovação formal da etapa anterior.")
    for numero, nome, resumo, laminas in FASES:
        p = _par(doc, antes=8, depois=4, justificado=True)
        _run(p, f"{numero} {nome} — ", estilo="b")
        _run(p, resumo)
        for lamina in laminas:
            p = _par(doc, depois=2, recuo=1.0)
            _run(p, f"-   {lamina}")

    # ===== 4 – Cronograma =====
    _titulo_secao(doc, "4", "CRONOGRAMA DE ENTREGAS")
    for segs in CRONOGRAMA:
        p = _par(doc, depois=4, recuo=1.0, justificado=True)
        _rich(p, segs)

    # ===== 5 – Investimento, pagamento e serviços adicionais =====
    _titulo_secao(doc, "5", "INVESTIMENTOS E FORMA DE PAGAMENTO")
    bloco_investimento(doc, "5.1", fin)
    bloco_pagamento(doc, "5.2", fin, PARCELAS_PAGAMENTO)

    _subtitulo(doc, "5.3 SERVIÇOS ADICIONAIS (ACOMPANHAMENTO E GESTÃO):")
    _bullet(doc, [
        ("Taxa de Acompanhamento de Obra e Gestão de Compras:", "b"),
        (f" incidência de {TAXA_ACOMPANHAMENTO_PCT}% "
         f"({'dez' if TAXA_ACOMPANHAMENTO_PCT == 10 else TAXA_ACOMPANHAMENTO_PCT} por cento) "
         "sobre o valor total dos orçamentos, produtos, mobiliários e serviços gerenciados "
         "pelo escritório.", ""),
    ])
    _bullet(doc, [
        ("Hora Técnica (Visitas In Loco):", "b"),
        (f" {brl(HORA_TECNICA)}, com previsão de contratação mínima de 02 (duas) horas por "
         "saída para supervisão em obra ou acompanhamento em lojas de fornecedores.", ""),
    ])

    # ===== 6 – Considerações gerais =====
    _titulo_secao(doc, "6", "CONSIDERAÇÕES GERAIS E RESPONSABILIDADES")
    for segs in CONSIDERACOES:
        _bullet(doc, segs)

    assinatura(doc, data)
