"""Leitura de print (e-mail, WhatsApp, briefing) → pedido em texto estruturado.

DUAS ETAPAS, de propósito. Ler e classificar na mesma chamada é o que fazia a
leitura perder item: num e-mail com 39 ambientes listados, o modelo gastava a
atenção decidindo categoria e devolvia 11 linhas, resumindo o resto. Separado:

1. TRANSCREVER (visão, sem catálogo): copiar todas as linhas do print, na
   ordem, com os cabeçalhos de seção. Só copiar — nenhuma decisão a tomar.
2. CLASSIFICAR (texto, com catálogo): pegar a transcrição literal e dizer em
   que categoria cada linha entra. Sem imagem no meio, com a lista inteira à
   vista, contar 39 linhas e devolver 39 é trabalho que o modelo faz bem.

O chat é stateless: o front reenvia a conversa inteira a cada mensagem, e com
ela o base64 do print. As duas etapas rodam UMA vez por print — o resultado
fica em cache pelo hash do conteúdo da imagem, e da segunda rodada em diante o
que segue para o modelo é só o texto.
"""
from __future__ import annotations

import hashlib
import os
from collections import OrderedDict

from app.dominio.precos import TabelaPrecos
from app.ia.visao import Imagem

CACHE_MAX = 128

# ---------------------------------------------------------------- etapa 1

_PROMPT_TRANSCRICAO = """Você transcreve PRINTS (e-mail, WhatsApp, briefing) para
outro assistente ler depois. Você NÃO interpreta, NÃO classifica, NÃO resume,
NÃO comenta: você COPIA. Devolva só o bloco do formato no fim.

COPIE TODAS AS LINHAS, na ordem em que aparecem, uma por linha. Esta é a regra
mais importante de todas. Um pedido de proposta costuma trazer 30 ou 40 linhas
de ambientes, e cada linha que você deixar de copiar é um item que a proposta
não vai cobrar — dinheiro que o escritório perde. Não agrupe ("12 ambientes
internos"), não resuma ("lista de ambientes"), não pule linha repetida, não
pare no meio da lista, não escreva "e assim por diante". Lista longa é normal:
copie até a última linha.

NÚMERO É SAGRADO. "2º ao 13º Pavimento Tipo" se copia "2º ao 13º Pavimento
Tipo", nunca "2º ao 3º". Faixas de andar, quantidades, medidas, durações e
valores saem caractere por caractere, do jeito que estão. Se um dígito estiver
ilegível, copie a linha e marque com (?) no fim — não adivinhe.

CABEÇALHO DE SEÇÃO — linha de título, em negrito, caixa alta ou com fundo
cinza, como "AMBIENTES INTERNOS - TÉRREO" ou "O escopo previsto contempla:" —
copie como "## <texto>". Ele não é item; é o título das linhas abaixo dele, e
o outro assistente precisa dele para saber a que grupo cada linha pertence.

Outras regras de cópia:
- Linha sem quantidade explícita: copie como está. Não invente "1".
- Vários prints na mesma mensagem são partes da MESMA tela, em sequência
  (a pessoa rolou e foi printando). Junte tudo numa transcrição só, na ordem.
  Linha que aparece no fim de um print e no começo do seguinte é a MESMA
  linha: copie uma vez.
- Texto cortado pela borda do print: copie o que dá para ler e marque
  (cortado) no fim da linha.
- Anexos, assinatura de e-mail, aviso de confidencialidade e barra de botões
  do programa não são conteúdo: deixe de fora.
- Se a imagem não for um pedido (conversa solta, foto qualquer), escreva
  "CORPO:" e, abaixo, só a linha "nada que pareça um pedido".

FORMATO (texto puro; o único markdown permitido é o "##" dos cabeçalhos):
DE: <nome e empresa de quem enviou, ou "não informado">
PARA: <nomes e empresas de quem recebeu, ou "não informado">
ASSUNTO: <assunto, ou "não informado">
CORPO:
<todas as linhas, na ordem em que aparecem>"""

# ---------------------------------------------------------------- etapa 2

_PROMPT_CLASSIFICACAO = """Você organiza a transcrição literal de um print de
pedido para o assistente de propostas do Grupo Flying. Não converse, não
cumprimente, não comente: devolva SÓ o bloco no formato do fim.

{catalogo}

CADA LINHA DE ITEM DA TRANSCRIÇÃO VIRA UMA LINHA EM ITENS. A transcrição já
tem tudo que o cliente pediu; a sua obrigação é não perder nada pelo caminho.
Trinta ambientes na transcrição são trinta linhas em ITENS. Não agrupe, não
resuma, não corte a lista, não escreva "e os demais ambientes". Antes de
responder, conte as linhas de item da transcrição e confira que ITENS tem o
mesmo tanto.

CABEÇALHO DE SEÇÃO (linha começando com "##") não é item: é o grupo das linhas
abaixo dele, e é ele que decide a categoria delas.
- "ambientes internos", "áreas internas", "interna" → ilustrações internas.
- "ambientes externos", "áreas externas", "fachada", "implantação" → a
  categoria externa/planta que o catálogo tiver para isso.
- seção de "plantas", "planta humanizada", "tipologias" → plantas.
- seção de filme, vídeo ou take → a categoria de filme do catálogo.
Quando a mesma descrição aparece em duas seções ("Fitness externo" no térreo e
na cobertura), são DOIS itens — e o grupo entra na descrição para distinguir:
"Fitness externo (cobertura)".

A/C É PESSOA DO CLIENTE. Num print de e-mail, quem está em PARA costuma ser
gente NOSSA (Flying Studio, Rinno Films, NID Studio, Grupo Flying): essa pessoa
NUNCA é o A/C. O A/C é quem pediu a proposta — normalmente quem está em DE, ou
alguém citado como responsável do lado do cliente. Se só houver nome de
empresa, A/C é "não informado".

CONSTRUTORA é a incorporadora/construtora dona do empreendimento. Quando uma
coordenadora de projetos, escritório de arquitetura ou agência pede "em nome
de" outra empresa, a CONSTRUTORA é a empresa em nome de quem se pede, e quem
pediu vira o A/C.

REGRA DE RIGIDEZ: pedido vago ("umas internas do apto tipo", "aquele vídeo de
sempre"), quantidade sem número, item que cabe em duas categorias ou serviço
que não é imagem vão para DÚVIDAS, com 2-3 candidatos do catálogo. Mas item em
dúvida NÃO SOME: ele entra nos DOIS lugares — em ITENS, com o melhor encaixe,
para a pessoa ver o item na tela, e em DÚVIDAS, para o chat confirmar. Linha
sob um cabeçalho que já diz interno/externo/planta não é dúvida: a seção
resolveu a categoria.

Outras regras:
- Nunca invente construtora, empreendimento, A/C, item, quantidade ou preço.
  O que não estiver na transcrição vai como "não informado".
- Quantidade sem número ("umas", "algumas", "várias") é DÚVIDA — não arredonde.
  Linha sem quantidade nenhuma, numa lista de ambientes, é 1.
- Copie a descrição como está na transcrição, inclusive faixas de andar
  ("Implantação 2º ao 13º Pavimento Tipo"). Não encurte nem corrija número.
- Não prefixe com "Perspectiva": o gerador faz isso.
- Preço/valor que apareça no print vai só em OBSERVAÇÕES, nunca como item.
- Minha Casa Minha Vida (MCMV, faixa, raiz) no print: registre em OBSERVAÇÕES.

FORMATO DA RESPOSTA (texto puro, sem markdown, exatamente estes rótulos):
CONSTRUTORA: <nome ou "não informado">
EMPREENDIMENTO: <nome ou "não informado">
A/C: <nome ou "não informado">
ITENS:
- <categoria do catálogo> | <descrição do item> | <quantidade>
(uma linha por item; se não houver item claro, escreva "- nenhum item claro")
DÚVIDAS:
- <trecho literal do print> | candidatos: <2-3 itens ou categorias do catálogo>
(se não houver, escreva "- nenhuma")
OBSERVAÇÕES: <uma linha, ou "nenhuma">"""

ABERTURA = "[LEITURA DO PRINT ANEXADO — vale como pedido do usuário]"
FECHAMENTO = ("[FIM DA LEITURA] Use CONSTRUTORA/EMPREENDIMENTO/A/C e os ITENS como se o "
              "usuário tivesse digitado. TODA linha de ITENS vira uma entrada na "
              "precificação — não resuma nem corte a lista. Cada linha de DÚVIDAS é uma "
              "pergunta a fazer depois de precificar.")

# hash(imagem + prompts) -> leitura pronta. Processo único, memória: o pior
# caso de um miss (restart, outro worker) é reler o print.
_cache: OrderedDict[str, str] = OrderedDict()


def _catalogo_para_prompt(tabela: TabelaPrecos) -> str:
    linhas = []
    for cat in tabela.categorias():
        meta = tabela.meta(cat)
        descricoes = "; ".join(item["descricao"] for item in tabela.dados[cat].get("tabela", []))
        linhas.append(f"- {meta['rotulo']} ({cat}): {descricoes}")
    return "CATÁLOGO OFICIAL (única fonte de classificação):\n" + "\n".join(linhas)


def montar_prompt(tabela: TabelaPrecos) -> str:
    """Prompt da etapa 2 — o que depende do catálogo."""
    return _PROMPT_CLASSIFICACAO.format(catalogo=_catalogo_para_prompt(tabela))


def prompt_transcricao() -> str:
    """Prompt da etapa 1 — sem catálogo: aqui só se copia."""
    return _PROMPT_TRANSCRICAO


def _modelo_visao() -> str:
    return os.getenv("OPENAI_MODEL_VISAO", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


def _modelo_texto() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _chamar_modelo(prompt: str, imagens: list[Imagem]) -> str:
    """Etapa 1: a imagem vira texto. `detail: high` é o que permite ler a
    letra pequena de um print de e-mail — sem isso, faixa de andar vira
    número errado."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    conteudo: list[dict] = [{"type": "text", "text": "Transcreva este print, linha por linha."}]
    conteudo += [{"type": "image_url", "image_url": {"url": img.url, "detail": "high"}}
                 for img in imagens]
    resp = client.chat.completions.create(
        model=_modelo_visao(),
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": conteudo}],
        temperature=0,
    )
    return (resp.choices[0].message.content or "").strip()


def _chamar_modelo_texto(prompt: str, transcricao: str) -> str:
    """Etapa 2: a transcrição literal vira o bloco estruturado. Sem imagem —
    o modelo enxerga a lista inteira de uma vez e consegue contá-la."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=_modelo_texto(),
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": f"TRANSCRIÇÃO DO PRINT:\n{transcricao}"}],
        temperature=0,
    )
    return (resp.choices[0].message.content or "").strip()


def _chave(imagens: list[Imagem], prompt: str) -> str:
    h = hashlib.sha256(prompt.encode())
    h.update(_PROMPT_TRANSCRICAO.encode())
    for img in imagens:
        h.update(img.hash.encode())
    return h.hexdigest()


def transcrever(imagens: list[Imagem], tabela: TabelaPrecos) -> str:
    """Print(s) → bloco estruturado, pelas duas etapas, lido uma única vez.

    Rodadas seguintes com os mesmos prints acertam o cache e não gastam nenhum
    token de imagem.
    """
    prompt_classificacao = montar_prompt(tabela)
    chave = _chave(imagens, prompt_classificacao)
    if chave in _cache:
        _cache.move_to_end(chave)
        return _cache[chave]

    literal = _chamar_modelo(_PROMPT_TRANSCRICAO, imagens)
    texto = _chamar_modelo_texto(prompt_classificacao, literal)
    _cache[chave] = texto
    _cache.move_to_end(chave)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)
    return texto


def em_bloco(transcricao: str) -> str:
    """Embrulha a leitura para entrar no histórico como mensagem de texto."""
    return f"{ABERTURA}\n{transcricao}\n{FECHAMENTO}"
