"""Roll (PDF, print ou texto colado) → seções e itens.

O roll que chega já vem com as suas próprias seções escritas ("2.2 Ilustrações
Internas"), e é ELA que vale: quem montou aquele roll decidiu onde cada
ambiente entra, e na Tavares a sauna foi para a área externa. O modelo aqui
copia essa estrutura; não a reinventa.

A regra de ambiente de `app/dominio/roll.py` entra depois, e só em dois
lugares: preenche o que veio sem seção (uma lista solta colada no campo) e
AVISA quando o que está escrito no roll discorda dela. Avisa — não corrige.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from app.docx.formatos import MESES_PT
from app.dominio.roll import TIPOS, TIPOS_DE_IMAGEM, classificar, parece_tipologia
from app.dominio.texto import normalizar
from app.ia.visao import Imagem

_PROMPT = """Você lê um ROLL DE IMAGENS do grupo Flying/Rinno/NID e devolve a
estrutura dele em JSON. O roll é a lista do que vai ENTRAR EM PRODUÇÃO — cada
perspectiva, cada planta, cada serviço — e ele NÃO tem preço nenhum. Se
aparecer valor, ignore o valor e mantenha o item.

COPIE TODAS AS LINHAS. Um roll tem 30, 40 linhas de ambientes, e cada linha que
você deixar de copiar é uma imagem que some da produção. Não agrupe, não
resuma, não escreva "e assim por diante". Lista longa é normal: vá até o fim.

NÚMERO É SAGRADO. "Implantação do pavimento (2º ao 12º)" se copia inteiro,
nunca "(2º ao 3º)". Tipologias ("Tipo 3 (2 Dormitórios)"), faixas de andar e
quantidades saem caractere por caractere.

AS SEÇÕES DO ROLL MANDAM. Se o documento já diz "2.1 Ilustrações Externas",
"2.2 Ilustrações Internas", "2.3 Plantas Baixas", respeite exatamente o que
está escrito lá: cada item vai para a seção embaixo da qual ele aparece, mesmo
que você ache que ele devia estar em outra. Quem montou o roll decidiu.

SÓ QUANDO NÃO HOUVER SEÇÃO NENHUMA é que você decide, assim:
- externas: o que se vê de fora ou a céu aberto — fachada, portaria, piscina,
  rooftop, solarium, pet place, fireplace, cine open, web garden, redário,
  voo de pássaro, fotomontagem, qualquer coisa com "externo/open/aberto";
- internas: ambiente fechado — lobby, delivery, locker, lavanderia, pet care,
  coworking, podcast, gourmet, jogos, academia, studio, living de cada
  tipologia, salão de festas, bicicletário;
- plantas: desenho técnico — implantação (térreo, cobertura, pavimento) e a
  planta de cada tipo, inclusive "Tipo 3 (2 Dormitórios)" sem a palavra
  "planta" na frente.
Na dúvida use "" no tipo: alguém confere. Chutar a seção é pior do que deixar
em branco.

SERVIÇO É BLOCO À PARTE. "Desenvolvimento de Aplicação Web – Para Tela Touch",
"Maquete Eletrônica", "Vista Virtual Web", "Um Filme Conceito de até 2:30":
tipo "servico", `titulo` com o nome completo como está escrito, e `itens` com
as linhas numeradas embaixo dele (o escopo). Serviço sem escopo escrito fica
com `itens` vazio.

Devolva SÓ este JSON, sem nenhum texto em volta:

{
  "cliente": {"empresa": "OUSY", "ref": "Vila Mariana"},
  "aprovado_em": "2026-06-30",
  "blocos": [
    {"tipo": "externas", "titulo": "Ilustrações Externas",
     "itens": ["Fachada noturna conceitual", "Portaria de acesso"]},
    {"tipo": "servico", "titulo": "Desenvolvimento de Aplicação Web – Para Web Touch",
     "itens": ["Catálogo Digital Interativo", "Apresentação do Empreendimento"]}
  ]
}

`cliente.empresa` é a construtora/incorporadora do cabeçalho ("OUSY - REF:
VILA MARIANA" -> empresa "OUSY", ref "Vila Mariana"). `aprovado_em` é a data
do pé do documento em AAAA-MM-DD; sem data no roll, use null."""


# ------------------------------------------------------------------ direto

# Roll exportado do Word tem forma fixa: cabeçalho "CLIENTE - REF: X", seções
# numeradas com dois níveis ("2.1 – Ilustrações Externas") e itens numerados
# com um nível ("1. Fachada diurna"). Isso se lê com regra, não com modelo:
# sai exato, sai de graça e sai sem depender de chave de API.
_RE_CABECALHO = re.compile(r"^(?P<empresa>.+?)\s+-\s+REF:\s*(?P<ref>.+)$", re.I)
_RE_SECAO = re.compile(r"^\s*\d+(?:\.\d+)+\.?\s*[–—-]?\s*(?P<titulo>\S.*?)\s*$")
_RE_ITEM = re.compile(r"^\s*\d+[.)]\s+(?P<item>\S.*?)[;.]?\s*$")
_RE_BULLET = re.compile(r"^\s*[•·*]\s*(?P<item>\S.*?)\s*$")
_RE_APROVADO = re.compile(r"aprovado em:\s*(?P<quando>.+?)\.?\s*$", re.I)
_RE_DATA_PT = re.compile(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", re.I)


def _tipo_do_titulo(titulo: str) -> str:
    """Seção de imagem pelo título. Título que mistura duas ("Ilustrações
    Externas/Internas/Plantas") não é chutado: fica para confirmar."""
    t = normalizar(titulo)
    achados = [nome for nome, marca in
               (("externas", "externa"), ("internas", "interna"), ("plantas", "planta"))
               if marca in t]
    if len(achados) == 1:
        return achados[0]
    if len(achados) > 1:
        return ""
    return "servico"


def _data_pt(texto: str) -> str | None:
    m = _RE_DATA_PT.search(texto)
    if not m:
        return None
    dia, mes, ano = m.groups()
    mes_norm = normalizar(mes)
    for i, nome in enumerate(MESES_PT, start=1):
        if normalizar(nome) == mes_norm:
            return f"{int(ano):04d}-{i:02d}-{int(dia):02d}"
    return None


def interpretar_texto(texto: str) -> dict[str, Any] | None:
    """O roll lido por regra. `None` quando o texto não tem a forma de roll.

    Só devolve alguma coisa se achar pelo menos uma seção COM item — texto
    solto e roll escaneado caem no modelo, que é o que sabe lidar com eles.
    """
    cliente = {"empresa": "", "ref": ""}
    blocos: list[dict[str, Any]] = []
    atual: dict[str, Any] | None = None
    aprovado: str | None = None

    for linha in texto.splitlines():
        crua = linha.strip()
        if not crua:
            continue
        if m := _RE_APROVADO.search(crua):
            aprovado = _data_pt(m.group("quando"))
            continue
        if not cliente["empresa"] and (m := _RE_CABECALHO.match(crua)):
            cliente = {"empresa": m.group("empresa").strip(),
                       "ref": m.group("ref").strip().title()}
            continue
        if m := _RE_SECAO.match(crua):
            titulo = m.group("titulo")
            tipo = _tipo_do_titulo(titulo)
            atual = {"tipo": tipo, "titulo": titulo, "itens": []}
            blocos.append(atual)
            continue
        if atual is None:
            continue
        item = None
        if m := (_RE_ITEM.match(crua) or _RE_BULLET.match(crua)):
            item = m.group("item").strip()
        elif atual["tipo"] == "servico" and not atual["itens"]:
            # Serviço descrito em prosa, sem lista: "Conteúdo: 10 Pílulas de
            # 15 segundos cada". Sem isto a seção inteira sumiria do roll.
            item = crua
        if item is None:
            continue
        # "Este item inclui:" é a abertura do escopo, não um item dele.
        if normalizar(item).rstrip(":").endswith("inclui"):
            continue
        atual["itens"].append(item)

    # Seção que ficou sem item é cabeçalho-guarda-chuva ("2.1 Ilustrações
    # Externas/Internas/Plantas" com as três subseções embaixo): some.
    blocos = [b for b in blocos if b["itens"]]
    if not blocos:
        return None
    return arrumar({"cliente": cliente, "aprovado_em": aprovado, "blocos": blocos})


def _modelo_texto() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _modelo_visao() -> str:
    return os.getenv("OPENAI_MODEL_VISAO", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


def prompt() -> str:
    return _PROMPT


def _cru(conteudo: list[dict] | str, modelo: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": _PROMPT},
                  {"role": "user", "content": conteudo}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return (resp.choices[0].message.content or "").strip()


def ler(texto: str = "", imagens: list[Imagem] | None = None) -> dict[str, Any]:
    """O roll como JSON. Aceita o texto do PDF, texto colado, ou print(s)."""
    # Roll exportado do Word se lê por regra: exato e sem chamar modelo.
    if texto and not imagens:
        if direto := interpretar_texto(texto):
            return direto
    if imagens:
        conteudo: list[dict] = [{"type": "text",
                                 "text": texto or "Leia este roll de imagens."}]
        conteudo += [{"type": "image_url", "image_url": {"url": i.url, "detail": "high"}}
                     for i in imagens]
        cru = _cru(conteudo, _modelo_visao())
    else:
        cru = _cru(f"ROLL:\n{texto}", _modelo_texto())
    try:
        return arrumar(json.loads(cru))
    except json.JSONDecodeError as e:
        raise ValueError(f"A leitura do roll não voltou em JSON: {cru[:200]}") from e


def arrumar(bruto: dict[str, Any]) -> dict[str, Any]:
    """Normaliza o que o modelo devolveu e confere contra a regra de ambiente.

    Item sem seção ganha a que a regra disser; item que a regra também não
    sabe fica em "a confirmar". O que a regra discorda do roll vira AVISO, não
    correção: as seções escritas no roll mandam.
    """
    blocos: list[dict[str, Any]] = []
    avisos: list[str] = []
    soltos: list[str] = []

    for b in bruto.get("blocos") or []:
        tipo = (b.get("tipo") or "").strip().lower()
        itens = [str(i).strip() for i in (b.get("itens") or []) if str(i).strip()]
        titulo = (b.get("titulo") or "").strip()
        if tipo == "servico" or (not tipo and titulo and not itens):
            blocos.append({"tipo": "servico", "titulo": titulo, "itens": itens})
            continue
        if tipo not in TIPOS_DE_IMAGEM:
            # Seção com título próprio que mistura as três ("Ilustrações
            # Externas/Internas/Plantas") continua sendo uma seção: perde-la
            # aqui apagaria o "40 Perspectivas a Definir" do roll inicial.
            if titulo:
                blocos.append({"tipo": "", "titulo": titulo, "itens": itens})
                avisos.append(
                    f'"{titulo}" não diz se é externa, interna ou planta — '
                    f"{len(itens)} item(ns) esperando a seção."
                )
            else:
                soltos += itens
            continue
        for item in itens:
            palpite = classificar(item)
            if palpite and palpite != tipo and not parece_tipologia(item):
                avisos.append(f'"{item}" está em {tipo} e parece de {palpite} — confira.')
        blocos.append({"tipo": tipo, "titulo": titulo, "itens": itens})

    # Lista colada sem seção nenhuma: aí sim a regra decide.
    if soltos:
        por_tipo: dict[str, list[str]] = {}
        for item in soltos:
            por_tipo.setdefault(classificar(item) or "", []).append(item)
        for tipo in TIPOS_DE_IMAGEM:
            if por_tipo.get(tipo):
                blocos.append({"tipo": tipo, "titulo": "", "itens": por_tipo[tipo]})
        if por_tipo.get(""):
            blocos.append({"tipo": "", "titulo": "A confirmar", "itens": por_tipo[""]})
            avisos.append(
                f"{len(por_tipo[''])} item(ns) sem seção que a regra não resolve: "
                f"{', '.join(por_tipo[''][:4])}. Diga em qual entram."
            )

    return {
        "cliente": {
            "empresa": ((bruto.get("cliente") or {}).get("empresa") or "").strip(),
            "ref": ((bruto.get("cliente") or {}).get("ref") or "").strip(),
        },
        "aprovado_em": (bruto.get("aprovado_em") or None),
        "blocos": _ordenar(_juntar(blocos)),
        "avisos": avisos,
    }


def _ordenar(blocos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A ordem do documento: externas, internas, plantas, serviços — e o que
    ficou para confirmar por último, onde não passa despercebido."""
    def peso(b):
        tipo = b["tipo"]
        if tipo in TIPOS_DE_IMAGEM:
            return TIPOS_DE_IMAGEM.index(tipo)
        return len(TIPOS_DE_IMAGEM) + (0 if tipo == "servico" else 1)

    return sorted(blocos, key=peso)


def _juntar(blocos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duas seções do mesmo tipo viram uma — roll partido em páginas chega
    assim, com "Ilustrações Internas (cont.)" repetindo o cabeçalho."""
    saida: list[dict[str, Any]] = []
    indice: dict[str, int] = {}
    for b in blocos:
        tipo = b["tipo"]
        if tipo in TIPOS_DE_IMAGEM and tipo in indice:
            saida[indice[tipo]]["itens"] += b["itens"]
            continue
        if tipo in TIPOS_DE_IMAGEM:
            indice[tipo] = len(saida)
        saida.append(b)
    return saida


__all__ = ["TIPOS", "arrumar", "interpretar_texto", "ler", "prompt"]
