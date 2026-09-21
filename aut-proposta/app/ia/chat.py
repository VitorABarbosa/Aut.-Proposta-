"""Chat conversacional da proposta: OpenAI com ferramentas internas.

A IA conduz a conversa (descontraída, pergunta o que falta, aceita tudo de
uma vez) e usa ferramentas para QUALQUER número: precificar, listar
propostas do cliente e carregar proposta antiga para copiar. Stateless — o
front manda o histórico inteiro a cada rodada.

Print anexado não entra nessa reenvio caro: antes de falar com o modelo, cada
mensagem com imagem passa pelas guardas de `app.ia.visao` e é trocada pela
transcrição em texto de `app.ia.leitura_print`, que lê o print uma única vez
(cache por hash). Da segunda rodada em diante a conversa segue só com texto.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import psycopg

from app.db.repo_chat_log import registrar_rodada
from app.db.repo_precos import carregar_tabela_precos
from app.db.repo_propostas import listar_propostas, obter_estrutura_de_proposta
from app.dominio.precos import TabelaPrecos
from app.empresas import EMISSOR_PADRAO, EMPRESAS, empresa
from app.ia.leitura_print import em_bloco, transcrever
from app.ia.visao import MAX_IMAGENS, ImagemInvalida, normalizar_imagem
from app.servicos.proposta import levantar

SAUDACAO = "Oi, tudo bem? O que vamos fazer hoje?"
QUICK_REPLIES = ["Nova proposta", "Consultar cliente", "Copiar proposta anterior"]
MSG_SEM_IA = ("O chat precisa da IA e ela está indisponível agora — "
              "use a aba 'Texto direto', que funciona sem internet da IA.")
MAX_RODADAS = 5

# Todas as tabelas do grupo. Qual delas vale depende do emissor — quem
# cruza os dois é `app.empresas.resolver_tabela`.
TABELAS_PRECOS = tuple(t for emp in EMPRESAS.values() for t in emp.tabelas)

_BASE_PROMPT = """Você é o assistente de propostas do Grupo Flying. Tom descontraído,
direto e simpático, em português. Uma proposta tem: QUAL EMPRESA NOSSA emite,
construtora/incorporadora (cliente), empreendimento (ref), A/C (quem recebe) e
os itens — organizados pelas categorias do CATÁLOGO OFICIAL abaixo.

PRECIFIQUE PRIMEIRO, PERGUNTE DEPOIS. Se dá para identificar os itens, chame a
ferramenta AGORA, já na primeira resposta, com o que você tem. Campo do cliente
que não veio vai vazio ("") — o preview ao lado lista sozinho o que falta, e a
pessoa preenche lá. Interrogatório antes de precificar é o pior erro que você
pode cometer aqui: quem usa isto quer ver o valor na tela. Depois de precificar,
no MÁXIMO UMA pergunta, e só se a resposta mudar o preço.

AS TRÊS EMPRESAS — cada uma tem a SUA ferramenta de precificação:
- precificar_flying — Flying Studio: imagens, plantas, filmes 3D, tour
  virtual, drone e tecnologias interativas (D.sbrave, web touch).
- precificar_rinno — Rinno Films: filmes publicitários (conceito,
  produto/corretor, viral, institucional, documentário) e takes animados.
- precificar_nid — NID Studio: projeto de interiores, design de fachada, stand
  de vendas (PDV), apto modelo decorado e desenvolvimento de produto.
Escolher a ferramenta É escolher a empresa. Filme institucional, conceito,
produto, corretor, viral e documentário são SEMPRE precificar_rinno.

QUEM EMITE É SEMPRE UMA DAS NOSSAS TRÊS — nunca um nome que apareça no pedido.
Construtora, incorporadora, coordenadora de projetos, escritório de arquitetura,
agência: tudo isso é CLIENTE, nunca emissor. "A Masha Coordenação de Projetos,
em nome da SAE Engenharia, solicita proposta do Plano de Imagens" → emissor é a
Flying (é plano de imagens) e cliente é a SAE; não se pergunta "a empresa que
emite é a Masha?". Deduza pelo tipo de item:
- imagens, plantas, tour virtual, drone, maquete eletrônica, tecnologia
  interativa → precificar_flying
- qualquer filme e takes animados → precificar_rinno
- interiores, design de fachada, stand/PDV, apto modelo decorado, produto → precificar_nid
Só pergunte a empresa se o pedido misturar itens de duas delas.

NÃO PERGUNTE ISSO (assuma e siga):
- MCMV: assuma tabela_precos='padrao'. Só use 'mcmv' se o usuário falar em
  MCMV/faixa/raiz. Nunca pergunte "é MCMV ou tabela padrão?".
- Preço por imagem: só existe se o usuário der o número. Sem número, vale a
  tabela. Nunca pergunte "você já tem um preço por imagem definido?".
- A/C é PESSOA, um nome de gente ("Luis", "Madeleine"). Nome de empresa NÃO é
  A/C. Se não veio pessoa nenhuma, mande contato: "" e precifique — a pendência
  do preview cobra isso sozinha. Nunca ofereça uma empresa como A/C.
- Quantidade de item que é único por natureza (filme, tour, projeto, app): é 1.
- Confirmação do que o usuário acabou de escrever. Ele escreveu, está valendo.

O mesmo cliente costuma receber proposta de mais de uma empresa, mas CADA
PROPOSTA É DE UMA EMPRESA SÓ. Se o pedido misturar serviços de empresas
diferentes (ex.: imagens + filme da Rinno), avise e pergunte por qual começar —
depois é só fazer a outra.

UMA UNIDADE POR ITEM, SALVO SE DITO: filme, tour, projeto e app são um por
pedido — "um filme institucional" é UM item; não pergunte "quantas unidades".
Imagem é por cena: "três fachadas" são três entradas.

PREÇO FORA DA PLANILHA (dois campos, os dois em código, nunca calculados por
você):
- `ajuste_planilha_pct`: "planilha mais 10%", "com 10% em cima", "cliente novo"
  → 10; "planilha menos 5%" → -5. Entra no preço de cada item e NÃO aparece na
  proposta. É diferente de desconto, que aparece como linha.
- `preco_por_imagem`: "2.400 por imagem", "média de 2.200 a imagem", "mesmo
  valor por imagem do projeto anterior" → o número. Vale para todas as
  perspectivas e plantas; não mexe em filme, tour ou tecnologia.
- Preço de UM item: "institucional de 2 minutos por 15 mil" → o item vai como
  {{"descricao": "Filme institucional de até 2:00", "preco": 15000}}. Só
  quando o usuário disse o número; sem número, mande só a descrição.

FILME TEM VARIÁVEIS: duração, locução, 4K, quantidade de takes. A tabela é uma
referência por tipo (institucional, conceito, produto/corretor, viral,
documentário), não a regra. Escreva a duração na descrição ("de até 2:00"). Se o
usuário não disser o valor, precifique assim mesmo e pergunte DEPOIS, em uma
linha — a tabela entra como referência, não como valor fechado de outra duração.

{catalogo}

COMO ENTENDER O PEDIDO (releia a conversa inteira antes de responder):
- Junte o que já foi dito nas mensagens anteriores. NUNCA pergunte de novo algo
  que o usuário já respondeu, nem repita a pergunta que ele acabou de responder
  com outras palavras.
- Uma mensagem pode trazer várias informações de uma vez — aproveite todas
  antes de perguntar a próxima coisa.
- Entenda linguagem solta e quantidade por extenso: "três fachadas" = 3
  unidades; "mais duas" soma às que já existem; "tira uma" subtrai.
- Correção é ordem: "na verdade são 4", "troca o A/C pra Ana", "esquece as
  plantas" — aplique a mudança sobre a estrutura atual e precifique de novo.
- Sempre que a estrutura mudar, chame a ferramenta de precificação de novo: o
  preview ao lado é o resultado da ÚLTIMA chamada, não do que você escreveu.
- Se não entendeu o pedido, pergunte o que faltou em uma frase — não responda
  por aproximação nem mude de assunto.

PRINT ANEXADO: quando aparecer um bloco "[LEITURA DO PRINT ANEXADO]", ele vale
como pedido escrito pelo usuário. Use a construtora, o empreendimento, o A/C e
os ITENS que vierem ali e PRECIFIQUE: o que estiver como "não informado" vai
vazio e vira pendência no preview, não vira pergunta. A única coisa que se
pergunta de um print é cada linha de DÚVIDAS, com os candidatos citados — esses
trechos você nunca classifica por conta própria.
TODA LINHA DE ITENS VIRA UMA ENTRADA. A leitura já veio contada e organizada;
se ela traz 39 itens, a chamada da ferramenta leva 39. Não resuma, não agrupe,
não corte a lista no meio, não deixe de fora o que está no fim. Copie a
descrição como está na leitura, faixa de andar inclusive ("Implantação 2º ao
13º Pavimento Tipo") — número você nunca reescreve.

REGRA DE RIGIDEZ: se o pedido não casar claramente com um item do catálogo
acima, NÃO classifique por palpite. Pergunte ao usuário qual item corresponde,
citando 2-3 candidatos do catálogo. Um serviço que não é imagem NUNCA entra
como ilustração externa/interna. Vale igual (ou mais) para pedido vindo de
print, que costuma chegar em linguagem solta e sem quantidade explícita.

MCMV: se o usuário indicar que o empreendimento é Minha Casa Minha Vida
(MCMV/faixa/raiz), use tabela_precos='mcmv'. Vale só para a Flying; na dúvida,
use 'padrao' e siga — não pergunte.

REGRAS INEGOCIÁVEIS:
- Você NUNCA inventa nem calcula preço/valor. Todo número vem das ferramentas.
- Se uma ferramenta devolver {{"erro": ...}}, repasse o texto do erro ao usuário
  como está. Não troque por uma causa que você imaginou ("a categoria não foi
  reconhecida") nem peça para ele reformular: o erro já diz o que fazer.
- Para precificar (mesmo parcial), chame a ferramenta DA EMPRESA com a
  estrutura: cliente = {{empresa, ref, contato}}; cada categoria dela (nome
  entre parênteses no catálogo) = lista de itens (uma entrada por unidade,
  repita se houver mais de uma unidade igual).
- Para consultar propostas antigas, chame listar_propostas_cliente (sem o nome
  do cliente ela devolve as mais recentes de todos).
- Para copiar uma proposta mudando algo, chame carregar_proposta, ajuste a
  estrutura conforme o pedido e chame a ferramenta de precificação da empresa.
- MEMÓRIA DE FERRAMENTAS: você NÃO guarda resultados de ferramentas entre
  mensagens — a cada mensagem nova, ids e dados de propostas antigas precisam
  ser reobtidos. Se o usuário pedir para copiar/carregar e você não tiver o id
  NESTA rodada, chame listar_propostas_cliente de novo AGORA e encadeie com
  carregar_proposta na mesma rodada — nunca diga que "não conseguiu acessar"
  sem antes relistar.
- Depois de precificar, resuma os valores devolvidos e diga que o preview ao lado
  foi atualizado; se não houver pendências, diga que é só clicar em Gerar.

EXEMPLOS (pedidos reais → chamada certa; copie o padrão):
1. "filme viral pra archtech, projeto GOIANIA, A/C Luis, cobre 4k pelo filme"
   → precificar_rinno {{cliente: {{empresa: "Archtech", ref: "Goiânia", contato:
   "Luis"}}, rinno_filmes: [{{descricao: "Filme viral de até 1:00", preco: 4000}}]}}
2. "institucional de 2 minutos pra Turtita, A/C Madeleine, fechamos 15 mil"
   → precificar_rinno {{..., rinno_filmes: [{{descricao: "Filme institucional de
   até 2:00", preco: 15000}}]}} — a duração vai na descrição e o valor é o dito.
3. "Rinno pra OUSY, Vila Mariana, A/C Yuri: um conceito, um corretor e um viral"
   → precificar_rinno {{..., rinno_filmes: ["Filme conceito", "Filme corretor",
   "Filme viral"]}} — três itens, sem perguntar quantidade nem valor.
4. "Flying pra UNICOS, João Casseb, A/C Manoela: fotomontagem masterplan, voo de
   pássaro fase 01, praça de lazer; plantas: implantação masterplan. 2.400 por
   imagem" → precificar_flying {{..., externas: ["Fotomontagem masterplan", "Voo
   de pássaro fase 01", "Praça de lazer"], plantas: ["Implantação masterplan"],
   preco_por_imagem: 2400}}
5. "cliente novo, planilha mais 10%: GALLI, Aurora, A/C Daniel, 3 externas
   (fachada, piscina, playground)" → precificar_flying {{..., externas:
   ["Fachada", "Piscina", "Playground"], ajuste_planilha_pct: 10}} — ajuste, não
   desconto: desconto_pct fica 0.
6. "NID pra OUSY, Vila Mariana, A/C Yuri: design de fachada, apto modelo 3 dorm,
   interiores da piscina e da academia" → precificar_nid {{..., nid_fachada:
   ["Design de fachada"], nid_interiores: ["Apto modelo decorado 3 dorm",
   "Piscina (área comum)", "Academia (área comum)"]}}
7. "A Masha Coordenação de Projetos, em nome da SAE Engenharia, solicita
   proposta do Plano de Imagens do empreendimento SAE | GUANÁS. Escopo: 1
   fachada frente + lateral direita dia, 1 fachada fundo + lateral esquerda, 1
   implantação térreo, 1 planta humanizada tipologia A"
   → precificar_flying {{cliente: {{empresa: "SAE Engenharia", ref: "SAE |
   GUANÁS", contato: ""}}, externas: ["Fachada frente + lateral direita dia",
   "Fachada fundo + lateral esquerda"], plantas: ["Implantação térreo", "Planta
   humanizada tipologia A"]}} — precifica na hora: sem A/C (vai vazio), sem
   perguntar empresa que emite, sem perguntar MCMV, sem perguntar preço por
   imagem. Depois, uma linha: "Falta só o A/C para gerar."

FORMATO DAS RESPOSTAS:
- Texto simples, SEM markdown: nada de **negrito**, títulos, tabelas ou colchetes
  de link. Frases curtas; se listar, use hífen simples no começo da linha.
- NUNCA inclua URLs ou links em nenhuma resposta. Para baixar uma proposta,
  oriente: "é só baixar na aba Histórico".
"""

# Mantido para compatibilidade/inspeção (catálogo vazio — prompt real é
# montado por `_montar_system_prompt` com o catálogo carregado do banco).
SYSTEM_PROMPT = _BASE_PROMPT.format(catalogo="CATÁLOGO OFICIAL (única fonte de classificação):")


def _linhas_do_catalogo(tabela: TabelaPrecos) -> list[str]:
    linhas = []
    for cat in tabela.categorias():
        meta = tabela.meta(cat)
        itens = tabela.dados[cat].get("tabela", [])
        descricoes = "; ".join(item["descricao"] for item in itens)
        linhas.append(f"- {meta['rotulo']} ({cat}): {descricoes}")
    return linhas


def _montar_system_prompt(catalogos: dict[str, TabelaPrecos]) -> str:
    """Injeta o catálogo oficial das três empresas (rótulo + descrições, SEM
    preços) no prompt, agrupado por empresa — é assim que a IA sabe que
    `rinno_filmes` é da Rinno e não um item da Flying."""
    blocos = []
    for chave, tabela in catalogos.items():
        emp = empresa(chave)
        blocos.append(f"{emp.nome} (emissor={chave}):")
        blocos.extend(f"  {linha}" for linha in _linhas_do_catalogo(tabela))
    catalogo = ("CATÁLOGO OFICIAL (única fonte de classificação):\n"
                + "\n".join(blocos))
    return _BASE_PROMPT.format(catalogo=catalogo)


def _tabela_unificada(catalogos: dict[str, TabelaPrecos]) -> TabelaPrecos:
    """Uma TabelaPrecos com as categorias das três empresas, para o que precisa
    enxergar o grupo inteiro antes de saber o emissor: a leitura de print.

    A ordem recebe um deslocamento por empresa para as categorias não se
    embaralharem. Nada aqui precifica — precificação é sempre na tabela de uma
    empresa só, escolhida em `levantar`.
    """
    dados: dict = {}
    for posicao, tabela in enumerate(catalogos.values()):
        for cat in tabela.categorias():
            bloco = dict(tabela.dados[cat])
            bloco["_ordem"] = posicao * 100 + bloco.get("_ordem", 0)
            dados[cat] = bloco
    return TabelaPrecos(dados)


def _schema_estrutura(categorias: list[str], emissor: str | None = None) -> dict:
    """JSON Schema da estrutura de precificação.

    Com `emissor`, é o schema da ferramenta daquela empresa: só as categorias
    dela, só as tabelas dela, e sem campo `emissor` — a ferramenta já diz de
    quem é. Sem `emissor` (compatibilidade), o schema genérico com todas as
    categorias e o campo `emissor` obrigatório."""
    properties: dict[str, Any] = {}
    if emissor is None:
        properties["emissor"] = {
            "type": "string", "enum": list(EMPRESAS),
            "description": "Empresa do grupo que emite esta proposta: "
                           "'flying' (imagens/3D), 'rinno' (filmes) ou "
                           "'nid' (projeto de interiores).",
        }
    properties["cliente"] = {
            "type": "object",
            "description": "Dados do cliente da proposta.",
            "properties": {
                "empresa": {"type": "string", "description": "Construtora/incorporadora"},
                "ref": {"type": "string", "description": "Empreendimento/referência"},
                "contato": {"type": "string", "description": "A/C — quem recebe"},
            },
            "required": ["empresa"],
    }
    for cat in categorias:
        dona = _empresa_da_categoria(cat)
        properties[cat] = {
            "type": "array",
            "items": {"anyOf": [
                {"type": "string"},
                {"type": "object",
                 "properties": {"descricao": {"type": "string"},
                                "preco": {"type": ["number", "null"],
                                          "description": "Só quando o USUÁRIO disse o valor "
                                                         "deste item. Nunca invente."}},
                 "required": ["descricao"], "additionalProperties": False},
            ]},
            "description": f"[{dona}] Itens da categoria '{cat}', uma entrada por unidade: a "
                           f"descrição (com duração, se houver) ou {{descricao, preco}} quando "
                           f"o usuário fechou o valor daquele item. Use SÓ com "
                           f"emissor='{_emissor_da_categoria(cat)}'.",
        }
    properties["desconto_pct"] = {"type": "number", "description": "Percentual de desconto (0 se não houver). Aparece na proposta como linha de desconto."}
    properties["desconto_label"] = {"type": ["string", "null"], "description": "Rótulo do desconto, se houver"}
    properties["ajuste_planilha_pct"] = {
        "type": "number",
        "description": "Ajuste sobre a tabela, em %, aplicado no preço de cada item e INVISÍVEL "
                       "na proposta: 'planilha + 10%' (cliente novo) = 10; 'planilha - 5%' = -5. "
                       "0 se não houver. Não confundir com desconto.",
    }
    properties["preco_por_imagem"] = {
        "type": ["number", "null"],
        "description": "Preço fixo por imagem, em reais, quando o cliente fecha um valor único "
                       "para todas as perspectivas e plantas (ex.: 'R$ 2.400 a imagem'). "
                       "null se não houver. Só afeta categorias de imagem.",
    }
    properties["estrategia"] = {"type": "string", "enum": ["planilha", "historico"],
                                 "description": "Fonte de preços a usar"}
    tabelas = list(empresa(emissor).tabelas) if emissor else list(TABELAS_PRECOS)
    properties["tabela_precos"] = {"type": "string", "enum": tabelas,
                                    "description": "Tabela de preços da empresa. Flying: "
                                                   "'padrao' ou 'mcmv' (Minha Casa Minha "
                                                   "Vida); Rinno: 'rinno'; NID: 'nid'."}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["cliente"] if emissor else ["emissor", "cliente"],
    }


def _emissor_da_categoria(cat: str) -> str:
    """Rinno e NID têm prefixo; o resto é Flying."""
    for chave in EMPRESAS:
        if chave != EMISSOR_PADRAO and cat.startswith(f"{chave}_"):
            return chave
    return EMISSOR_PADRAO


def _empresa_da_categoria(cat: str) -> str:
    return empresa(_emissor_da_categoria(cat)).nome


def nome_da_ferramenta(emissor: str) -> str:
    return f"precificar_{emissor}"


def _emissor_da_ferramenta(nome: str) -> str | None:
    """'precificar_rinno' -> 'rinno'; qualquer outro nome -> None."""
    prefixo = "precificar_"
    if nome.startswith(prefixo) and nome[len(prefixo):] in EMPRESAS:
        return nome[len(prefixo):]
    return None


def _ferramentas(categorias_por_empresa: dict[str, list[str]]) -> list[dict]:
    """Uma ferramenta de precificação por empresa, cada uma só com as
    categorias e tabelas da própria. Escolher a ferramenta é escolher a
    empresa — `filmes` com emissor rinno deixa de ser possível, em vez de
    ser remapeado depois."""
    ferramentas = []
    for chave, categorias in categorias_por_empresa.items():
        emp = empresa(chave)
        ferramentas.append({"type": "function", "function": {
            "name": nome_da_ferramenta(chave),
            "description": f"Precifica uma proposta da {emp.nome} (preços oficiais/histórico "
                           "do cliente). Devolve valores, totais e pendências obrigatórias. "
                           "Use só para serviços dessa empresa.",
            "parameters": {"type": "object",
                           "properties": {"estrutura": _schema_estrutura(categorias, chave)},
                           "required": ["estrutura"]}}})
    return ferramentas + [
        {"type": "function", "function": {
            "name": "listar_propostas_cliente",
            "description": "Lista propostas já feitas (id, cliente, projeto, data, total), "
                           "mais recente primeiro. Sem 'cliente', lista de TODOS os "
                           "clientes — use assim para 'a proposta mais recente'.",
            "parameters": {"type": "object",
                           "properties": {"cliente": {
                               "type": "string",
                               "description": "Nome do cliente (opcional)"}},
                           "required": []}}},
        {"type": "function", "function": {
            "name": "carregar_proposta",
            "description": "Carrega a estrutura completa de uma proposta antiga pelo id "
                           "(o campo 'id' devolvido por listar_propostas_cliente), "
                           "para copiar/ajustar e depois precificar.",
            "parameters": {"type": "object", "properties": {"proposta_id": {"type": "integer"}},
                           "required": ["proposta_id"]}}},
    ]


# Mantido para compatibilidade/inspeção — schema/ferramentas reais são
# montados por request em `responder`, com as categorias do catálogo carregado.
FERRAMENTAS = _ferramentas({chave: [] for chave in EMPRESAS})


def modelo_configurado() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _chamar_modelo(mensagens_llm: list[dict], tools: list[dict]):
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=modelo_configurado(),
        messages=mensagens_llm,
        tools=tools,
        temperature=0.2,
    )
    return resp.choices[0].message


_CATEGORIAS_FALLBACK = ("externas", "internas", "plantas")


def _completar_estrutura(bruto: dict, categorias: list[str] | None = None) -> dict:
    """Rede de segurança: completa a estrutura mandada pelo modelo com defaults,
    tolerando formatos levemente errados (ex.: cliente como string solta)."""
    categorias = list(categorias) if categorias is not None else list(_CATEGORIAS_FALLBACK)
    bruto = bruto or {}
    estrutura = {
        "cliente": {"empresa": "CLIENTE", "ref": "", "contato": ""},
        **{cat: [] for cat in categorias},
        "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
        "ajuste_planilha_pct": 0, "preco_por_imagem": None,
        "mostrar_precos_individuais": False, "_avisos": [],
        "emissor": EMISSOR_PADRAO, "tabela_precos": "padrao",
    }
    for chave, valor in bruto.items():
        estrutura[chave] = valor

    cliente = estrutura.get("cliente")
    if isinstance(cliente, str):
        cliente = {"empresa": cliente, "ref": "", "contato": ""}
    elif not isinstance(cliente, dict):
        cliente = {"empresa": "CLIENTE", "ref": "", "contato": ""}
    else:
        cliente = {"empresa": cliente.get("empresa") or "CLIENTE",
                   "ref": cliente.get("ref") or "",
                   "contato": cliente.get("contato") or ""}
    estrutura["cliente"] = cliente

    for chave in categorias:
        itens = estrutura.get(chave)
        if not isinstance(itens, list):
            itens = []
        # String vira string; {descricao, preco} fica como está (o domínio lê os
        # dois); qualquer outra coisa vira texto para não derrubar a rodada.
        estrutura[chave] = [
            item if isinstance(item, dict) and item.get("descricao") else str(item)
            for item in itens if item not in (None, "")
        ]

    # Emissor e tabela têm de fechar entre si: emissor inválido vira o padrão,
    # e tabela que não é da empresa escolhida vira a padrão DELA. Sem isso um
    # 'mcmv' com emissor='rinno' viraria erro de ferramenta no meio da conversa.
    try:
        emp = empresa(estrutura.get("emissor"))
    except ValueError:
        emp = empresa(EMISSOR_PADRAO)
    estrutura["emissor"] = emp.chave
    if estrutura.get("tabela_precos") not in emp.tabelas:
        estrutura["tabela_precos"] = emp.tabela_padrao

    return estrutura


def _executar_ferramenta(conn: psycopg.Connection, nome: str, args: dict,
                          categorias: list[str] | None = None) -> tuple[str, dict | None]:
    """Devolve (resultado_json_para_a_ia, levantamento_ou_None)."""
    emissor_da_ferramenta = _emissor_da_ferramenta(nome)
    if nome == "precificar_proposta" or emissor_da_ferramenta:
        bruto = dict(args.get("estrutura") or {})
        if emissor_da_ferramenta:
            # A ferramenta manda: precificar_rinno é da Rinno, diga o que
            # disser um campo `emissor` perdido nos argumentos.
            bruto["emissor"] = emissor_da_ferramenta
        estrutura = _completar_estrutura(bruto, categorias)
        try:
            lev = levantar(conn, estrutura)
        except ValueError as exc:
            # Erro de entrada (ajuste absurdo, preço negativo): volta para a IA
            # com a instrução de repassar o texto tal qual — sem isso ela
            # "explica" com um palpite errado.
            return json.dumps({
                "erro": str(exc),
                "instrucao": "Repasse esta mensagem ao usuário exatamente como está, "
                             "sem inventar outra causa e sem pedir para ele reformular.",
            }, ensure_ascii=False), None
        estrutura = lev["estrutura"]  # já no namespace do emissor (filmes -> rinno_filmes)
        from app.api.main import _pendencias  # mesma regra de pendências da API
        lev_out = {
            "estrutura": estrutura,
            "fechado": lev["fechado"],
            "estrategia_usada": lev["estrategia_usada"],
            "avisos": lev["avisos"],
            "pendencias": _pendencias(estrutura, lev["fechado"]),
        }
        resumo = {
            "subtotal": lev["fechado"]["financeiro"]["subtotal"],
            "total": lev["fechado"]["financeiro"]["total"],
            "total_imagens": lev["fechado"]["orcamento"]["total_imagens"],
            "pendencias": lev_out["pendencias"],
            "avisos": lev["avisos"],
        }
        return json.dumps(resumo, ensure_ascii=False), lev_out
    if nome == "listar_propostas_cliente":
        # Sem docx_url: o bucket é privado e a IA não deve citar links —
        # download é pela aba Histórico.
        propostas = [{k: v for k, v in p.items() if k != "docx_url"}
                     for p in listar_propostas(conn, args.get("cliente") or None)]
        return json.dumps(propostas, ensure_ascii=False), None
    if nome == "carregar_proposta":
        est = obter_estrutura_de_proposta(conn, int(args["proposta_id"]))
        if est is None:
            return json.dumps(
                {"erro": f"proposta {args['proposta_id']} não encontrada — chame "
                         "listar_propostas_cliente para obter o id correto e tente de novo."},
                ensure_ascii=False), None
        return json.dumps(est, ensure_ascii=False), None
    return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), None


def _citar_propostas(nome: str, args: dict, resultado: str,
                     citadas: dict[int, dict]) -> None:
    """Coleta as propostas tocadas pelas ferramentas na rodada — o hub mostra
    botões de download (a IA não pode citar links: bucket privado)."""
    try:
        dados = json.loads(resultado)
    except (ValueError, TypeError):
        return
    if nome == "listar_propostas_cliente" and isinstance(dados, list):
        for p in dados[:5]:
            if isinstance(p, dict) and "id" in p:
                citadas[p["id"]] = {"id": p["id"], "cliente": p.get("cliente", ""),
                                    "referencia": p.get("referencia") or ""}
    elif nome == "carregar_proposta" and isinstance(dados, dict) and "erro" not in dados:
        pid = int(args.get("proposta_id") or 0)
        cli = dados.get("cliente") if isinstance(dados.get("cliente"), dict) else {}
        if pid:
            citadas[pid] = {"id": pid, "cliente": cli.get("empresa", ""),
                            "referencia": cli.get("ref") or ""}


def _separar_conteudo(content: Any) -> tuple[str, list[str]]:
    """Separa o `content` de uma mensagem em (texto, urls das imagens).

    Aceita o formato de partes da OpenAI — [{"type": "text", ...},
    {"type": "image_url", "image_url": {"url": ...}}] — e o `image_url` como
    string solta, que alguns clientes mandam.
    """
    if not isinstance(content, list):
        return (content if isinstance(content, str) else ""), []
    textos: list[str] = []
    urls: list[str] = []
    for parte in content:
        if isinstance(parte, str):
            textos.append(parte)
            continue
        if not isinstance(parte, dict):
            continue
        if parte.get("type") == "image_url" or "image_url" in parte:
            img = parte.get("image_url")
            url = img.get("url") if isinstance(img, dict) else img
            if isinstance(url, str):
                urls.append(url)
        elif isinstance(parte.get("text"), str):
            textos.append(parte["text"])
    return "\n".join(t for t in textos if t.strip()), urls


def _preparar_mensagens(mensagens: list[dict],
                        tabela: TabelaPrecos) -> tuple[list[dict], str | None]:
    """Troca cada mensagem com print pela sua transcrição em texto.

    Só o texto segue para o modelo da conversa: a imagem é lida uma vez e o
    resultado vem do cache nas rodadas seguintes (o front reenvia o histórico
    inteiro, base64 incluído, a cada mensagem).

    O segundo item devolvido é o conteúdo montado da última mensagem com print
    — o mesmo texto que foi para o modelo. O front pode gravá-lo no lugar da
    imagem e parar de reenviar o base64; a rodada seguinte fica idêntica para
    o modelo, e nem o cache precisa ser consultado.
    """
    preparadas: list[dict] = []
    transcricao: str | None = None
    for msg in mensagens:
        texto, urls = _separar_conteudo(msg.get("content"))
        if not urls:
            preparadas.append(msg)
            continue
        if len(urls) > MAX_IMAGENS:
            raise ImagemInvalida(
                f"Consigo ler até {MAX_IMAGENS} prints por mensagem. "
                "Manda os mais importantes primeiro.")
        imagens = [normalizar_imagem(url) for url in urls]
        conteudo = "\n\n".join(
            p for p in (texto, em_bloco(transcrever(imagens, tabela))) if p)
        transcricao = conteudo
        preparadas.append({**msg, "content": conteudo})
    return preparadas, transcricao


def _resposta(mensagem: str, *, quick_replies: list[str] | None = None,
              levantamento: dict | None = None,
              propostas_citadas: list[dict] | None = None,
              transcricao: str | None = None) -> dict[str, Any]:
    return {"mensagem": mensagem, "quick_replies": quick_replies or [],
            "levantamento": levantamento,
            "propostas_citadas": propostas_citadas or [],
            "transcricao": transcricao}


def responder(conn: psycopg.Connection, mensagens: list[dict],
              traco: list[dict] | None = None) -> dict[str, Any]:
    """Uma rodada do chat. `traco`, se passado, recebe cada chamada de
    ferramenta ({nome, args, resultado}) — é o que a avaliação lê.

    Toda rodada com mensagem fica registrada em chat_log (nunca derruba o
    chat): é a matéria-prima para medir e melhorar a inteligência.
    """
    if not mensagens:
        return _resposta(SAUDACAO, quick_replies=QUICK_REPLIES)
    traco = [] if traco is None else traco
    inicio = time.monotonic()
    resposta: dict[str, Any] | None = None
    erro: str | None = None
    try:
        resposta = _responder(conn, mensagens, traco)
        return resposta
    except Exception as exc:  # noqa: BLE001 — registra e propaga
        erro = repr(exc)
        raise
    finally:
        registrar_rodada(
            conn, modelo=modelo_configurado(), mensagens=mensagens, ferramentas=traco,
            resposta=resposta or {}, emissor=_emissor_do_traco(traco),
            duracao_ms=int((time.monotonic() - inicio) * 1000), erro=erro,
        )


def _emissor_do_traco(traco: list[dict]) -> str | None:
    for chamada in reversed(traco):
        emissor = _emissor_da_ferramenta(chamada.get("nome", ""))
        if emissor:
            return emissor
    return None


def _responder(conn: psycopg.Connection, mensagens: list[dict],
               traco: list[dict]) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return _resposta(MSG_SEM_IA)

    # Catálogo carregado 1x por request, fora do try/except abaixo (que só
    # cobre a conversa com o modelo): falha de banco deve propagar como nas
    # outras rotas, não virar MSG_SEM_IA silenciosamente.
    catalogos = {chave: carregar_tabela_precos(conn, emp.tabela_padrao)
                 for chave, emp in EMPRESAS.items()}
    tabela = _tabela_unificada(catalogos)
    categorias = tabela.categorias()
    system_prompt = _montar_system_prompt(catalogos)
    ferramentas = _ferramentas({chave: t.categorias() for chave, t in catalogos.items()})

    # Prints viram texto ANTES da conversa: guarda recusada é erro do usuário
    # (mensagem própria), falha da leitura cai no mesmo MSG_SEM_IA do chat.
    try:
        mensagens, transcricao = _preparar_mensagens(mensagens, tabela)
    except ImagemInvalida as exc:
        return _resposta(str(exc))
    except Exception:  # noqa: BLE001 — IA indisponível nunca derruba o chat
        return _resposta(MSG_SEM_IA)

    llm: list[dict] = [{"role": "system", "content": system_prompt}] + list(mensagens)
    levantamento: dict | None = None
    citadas: dict[int, dict] = {}
    try:
        for _ in range(MAX_RODADAS):
            msg = _chamar_modelo(llm, ferramentas)
            if not getattr(msg, "tool_calls", None):
                return _resposta(msg.content or "", levantamento=levantamento,
                                 propostas_citadas=list(citadas.values()),
                                 transcricao=transcricao)
            llm.append({"role": "assistant", "content": msg.content,
                        "tool_calls": [
                            {"id": tc.id, "type": "function",
                             "function": {"name": tc.function.name,
                                          "arguments": tc.function.arguments}}
                            for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                # Erro de ferramenta volta para a IA se corrigir na próxima
                # rodada; só falha de _chamar_modelo derruba para MSG_SEM_IA.
                args_tc: dict = {}
                try:
                    args_tc = json.loads(tc.function.arguments)
                    resultado, lev = _executar_ferramenta(
                        conn, tc.function.name, args_tc, categorias)
                except Exception as exc:  # noqa: BLE001
                    resultado, lev = json.dumps(
                        {"erro": f"argumentos inválidos para {tc.function.name}: "
                                 f"{exc}. Corrija e tente de novo."},
                        ensure_ascii=False), None
                if lev is not None:
                    levantamento = lev
                traco.append({"nome": tc.function.name, "args": args_tc, "resultado": resultado})
                _citar_propostas(tc.function.name, args_tc, resultado, citadas)
                llm.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
        return _resposta("Precisei de muitas etapas — pode repetir de forma mais direta?",
                         levantamento=levantamento,
                         propostas_citadas=list(citadas.values()),
                         transcricao=transcricao)
    except Exception:  # noqa: BLE001 — IA indisponível nunca derruba o chat
        return _resposta(MSG_SEM_IA)
