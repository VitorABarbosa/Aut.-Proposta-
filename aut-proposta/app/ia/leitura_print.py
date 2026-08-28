"""Leitura de print (e-mail, WhatsApp, briefing) → pedido em texto estruturado.

O chat é stateless: o front reenvia a conversa inteira a cada mensagem, e com
ela o base64 do print. Mandar a imagem para o modelo em todas as rodadas é
pagar seis vezes pela mesma leitura.

Aqui o print é lido UMA vez — o resultado é uma transcrição em texto, guardada
em cache pelo hash do conteúdo da imagem. Da segunda rodada em diante o mesmo
print cai no cache e o que segue para o modelo é só o texto.

A transcrição obedece à mesma regra de rigidez do chat: item que não casa
claramente com o catálogo vai para DÚVIDAS, com candidatos, para o chat
perguntar — nunca é chutado numa categoria.
"""
from __future__ import annotations

import hashlib
import os
from collections import OrderedDict

from app.dominio.precos import TabelaPrecos
from app.ia.visao import Imagem

CACHE_MAX = 128

_PROMPT = """Você lê PRINTS de e-mail, WhatsApp ou briefing e transcreve o pedido
em texto estruturado para outro assistente continuar a conversa. Não converse,
não cumprimente, não comente: devolva SÓ o bloco no formato pedido no fim.

Extraia exatamente quatro coisas:
1. CONSTRUTORA — a construtora/incorporadora que está contratando.
2. EMPREENDIMENTO — o nome do projeto/obra a que o pedido se refere.
3. A/C — a pessoa que recebe a proposta (quem escreveu, assinou ou foi citado
   como responsável).
4. ITENS — o que foi pedido, com quantidade.

{catalogo}

REGRA DE RIGIDEZ (a mais importante): print vem com linguagem solta — "3
fachadas noturnas", "umas internas do apto tipo", "aquele vídeo de sempre".
Só classifique um item numa categoria do catálogo quando o encaixe for ÓBVIO.
Qualquer dúvida — pedido vago, quantidade sem número, item que cabe em duas
categorias, serviço que não é imagem — vai para DÚVIDAS com 2-3 candidatos do
catálogo, NUNCA chutado numa categoria. Perguntar custa uma mensagem; errar a
classificação custa a proposta inteira.

Outras regras:
- Nunca invente construtora, empreendimento, A/C, item, quantidade ou preço.
  O que não estiver no print vai como "não informado".
- Quantidade sem número ("umas", "algumas", "várias") é DÚVIDA — não arredonde.
- Nome de ambiente curto e como está no print ("Fachada noturna", "Lobby",
  "Implantação"). Não prefixe com "Perspectiva".
- Preço/valor que apareça no print vai só em OBSERVAÇÕES, nunca como item.
- Se o print indicar Minha Casa Minha Vida (MCMV, faixa, raiz), registre em
  OBSERVAÇÕES.
- Se a imagem não for um pedido de proposta (conversa solta, foto qualquer),
  diga isso em OBSERVAÇÕES e deixe os quatro campos como "não informado".

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
              "usuário tivesse digitado. Cada linha de DÚVIDAS é uma pergunta a fazer — "
              "não classifique esses trechos por conta própria.")

# hash(imagem + catálogo) -> transcrição. Processo único, memória: o pior caso
# de um miss (restart, outro worker) é reler o print.
_cache: OrderedDict[str, str] = OrderedDict()


def _catalogo_para_prompt(tabela: TabelaPrecos) -> str:
    linhas = []
    for cat in tabela.categorias():
        meta = tabela.meta(cat)
        descricoes = "; ".join(item["descricao"] for item in tabela.dados[cat].get("tabela", []))
        linhas.append(f"- {meta['rotulo']} ({cat}): {descricoes}")
    return "CATÁLOGO OFICIAL (única fonte de classificação):\n" + "\n".join(linhas)


def montar_prompt(tabela: TabelaPrecos) -> str:
    return _PROMPT.format(catalogo=_catalogo_para_prompt(tabela))


def _chamar_modelo(prompt: str, imagens: list[Imagem]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    conteudo: list[dict] = [{"type": "text", "text": "Transcreva o pedido deste print."}]
    conteudo += [{"type": "image_url", "image_url": {"url": img.url, "detail": "high"}}
                 for img in imagens]
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_VISAO", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": conteudo}],
        temperature=0,
    )
    return (resp.choices[0].message.content or "").strip()


def _chave(imagens: list[Imagem], prompt: str) -> str:
    h = hashlib.sha256(prompt.encode())
    for img in imagens:
        h.update(img.hash.encode())
    return h.hexdigest()


def transcrever(imagens: list[Imagem], tabela: TabelaPrecos) -> str:
    """Transcrição do(s) print(s) em texto estruturado, lida uma única vez.

    Rodadas seguintes com os mesmos prints acertam o cache e não gastam nenhum
    token de imagem.
    """
    prompt = montar_prompt(tabela)
    chave = _chave(imagens, prompt)
    if chave in _cache:
        _cache.move_to_end(chave)
        return _cache[chave]

    texto = _chamar_modelo(prompt, imagens)
    _cache[chave] = texto
    _cache.move_to_end(chave)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)
    return texto


def em_bloco(transcricao: str) -> str:
    """Embrulha a transcrição para entrar no histórico como mensagem de texto."""
    return f"{ABERTURA}\n{transcricao}\n{FECHAMENTO}"
