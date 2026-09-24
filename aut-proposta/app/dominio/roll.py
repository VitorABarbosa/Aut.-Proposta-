"""O roll: a lista do que entra em produção, e como ela muda ao longo do projeto.

O roll não é a proposta. A proposta é o que foi vendido, com preço; o roll é o
que vai ser FEITO — cada perspectiva, cada planta, cada serviço, sem valor
nenhum — e ele se mexe: o cliente corta duas plantas, pede mais uma fachada,
troca um living de tipologia. Por isso ele tem versão, e a versão tem nome:

    Roll_Flying  ->  Roll_Flying_Atl  ->  Roll_Flying_Atl_1  ->  _Atl_2 ...

A cabeça do roll é a divisão das imagens em EXTERNAS, INTERNAS e PLANTAS, que
é como o estúdio conta o que produziu. A regra vem dos rolls reais:

  - externa  é o que se vê de fora ou a céu aberto: fachada, portaria, piscina,
    rooftop, solarium, pet place, fireplace, cine open, web garden, redário,
    voo de pássaro, fotomontagem;
  - interna  é ambiente fechado: lobby, delivery, locker, lavanderia, pet care,
    coworking, podcast, gourmet, jogos, academia, studio, living de cada
    tipologia;
  - planta   é desenho técnico humanizado: implantação (térreo, cobertura,
    pavimento) e a planta de cada tipo.

O qualificador ganha do ambiente: "Fitness externo" e "Apoio Gourmet" moram na
área externa mesmo tendo nome de sala. E o que a regra não resolve NÃO é
chutado: fica "a confirmar" e alguém decide, porque um item na seção errada
vira imagem cobrada errada lá na frente.
"""
from __future__ import annotations

import re
from typing import Any

from app.dominio.texto import normalizar

# Seções de imagem, na ordem em que saem no documento. `servico` não entra
# aqui: ele tem título próprio e escopo embaixo.
TIPOS_DE_IMAGEM = ("externas", "internas", "plantas")
TIPOS = (*TIPOS_DE_IMAGEM, "servico")

ROTULO = {
    "externas": "Ilustrações Externas",
    "internas": "Ilustrações Internas",
    "plantas": "Plantas Baixas",
}

# Desenho técnico dito com todas as letras. Vem antes de tudo porque "Planta
# Studio Tipo 1" tem "studio", que é nome de ambiente interno.
_PLANTA_EXPLICITA = re.compile(
    r"\b(planta\w*|implanta\w*|pavimento\w*|cobertura|setorizac\w*|layout|"
    r"variacao de sacada)\b"
)

# Tipologia sem nome de ambiente também é planta. Quem decide é a POSIÇÃO:
# "Tipo 3 (2 Dormitórios)" ABRE com a tipologia e é planta; "Living – Tipo 2
# (Studio)" abre com o ambiente e é perspectiva interna. Os dois existem no
# mesmo roll da Tavares, um em cada seção.
_TIPOLOGIA = re.compile(r"\b(tipo \d+|tipologia\w*|\d+ ?dorm\w*)\b")
_ABRE_COM_TIPOLOGIA = re.compile(r"^tipo \d+")

# Qualificador que joga o ambiente para fora, aconteça o que acontecer com o
# nome dele: "Fitness externo", "Cine Open", "Voo Rooftop", "Apoio Gourmet".
_QUALIFICADOR_EXTERNO = re.compile(
    r"\b(externa\w*|externo\w*|open|rooftop|roof top|aberto|descoberto|"
    r"voo|aerea|aereo|fotomontagem|fotodrone|drone|apoio)\b"
)

_EXTERNAS = re.compile(
    r"\b(fachada\w*|portaria|acesso|piscina|deck|solarium|solario|jardim|"
    r"paisagism\w*|playground|pet ?place|quadra|praca|praia|redario|lounge|"
    r"web garden|fireplace|espelho d\w*|churrasqueira|pergolado|mirante|"
    r"terraco|varanda|entorno|vizinhanca|rua|calcada)\b"
)

# "sauna" e "spa" ficam de fora de propósito: no roll da Tavares a sauna saiu
# na seção externa, e um item na seção errada é imagem cobrada errada — vira
# "a confirmar" e alguém decide.
_INTERNAS = re.compile(
    r"\b(lobby|hall|recepcao|delivery|locker|lavanderia|pet ?care|"
    r"coworking|co-working|podcast|gourmet|jogos|academia|fitness|studio|"
    r"living|sala|salao|festas|cinema|brinquedoteca|bicicletario|"
    r"apartamento|apto|decorado|suite|cozinha|banheiro|"
    r"escritorio|market|mercado|bar|vestiario|corredor|elevador)\b"
)


def classificar(descricao: str) -> str | None:
    """Em que seção do roll o ambiente entra. `None` = não dá para saber.

    Chutar aqui é pior do que perguntar: item na seção errada é imagem cobrada
    errada. O que não casa com nada volta para a pessoa confirmar.
    """
    texto = normalizar(descricao)
    if not texto:
        return None
    if _PLANTA_EXPLICITA.search(texto) or _ABRE_COM_TIPOLOGIA.match(texto):
        return "plantas"
    if _QUALIFICADOR_EXTERNO.search(texto):
        return "externas"
    if _EXTERNAS.search(texto):
        return "externas"
    if _INTERNAS.search(texto):
        return "internas"
    if _TIPOLOGIA.search(texto):
        return "plantas"
    return None


def parece_tipologia(descricao: str) -> bool:
    """"Tipo 2 (Studio)", "Tipo 3 (2 Dormitórios)": tipologia com nome de
    ambiente dentro. Na seção de plantas isso é o normal, não um engano — e
    sem isto todo roll abriria com um aviso que não é aviso de nada."""
    return bool(_TIPOLOGIA.search(normalizar(descricao)))


def numerar(blocos: list[dict[str, Any]], secao: int = 2) -> list[tuple[str, dict]]:
    """(numero, bloco) na ordem do documento: 2.1, 2.2, 2.3…

    A numeração é escrita na hora, nunca lida do arquivo: os rolls reais vêm
    com 2.1.1 num, 2.1 no outro, e o que vale é a ordem.
    """
    return [(f"{secao}.{i}", b) for i, b in enumerate(blocos, start=1)]


def total_de_imagens(blocos: list[dict[str, Any]]) -> int:
    """Quantas imagens o roll tem. Serviço não é imagem, e é essa conta que
    muda quando o cliente corta ou acrescenta."""
    return sum(len(b.get("itens") or []) for b in blocos
               if b.get("tipo") in TIPOS_DE_IMAGEM)


# Prefixo de escrita: o mesmo item aparece "Lobby" numa versão do roll e
# "Perspectiva Lobby" na seguinte. Comparar sem tirar isso faria a atualização
# da Tavares parecer troca de 11 ambientes, quando não mudou nada.
_PREFIXO_DE_ESCRITA = re.compile(r"^(perspectiva|planta|ilustracao|imagem|vista)s?\s+")


def _chave(item: str) -> str:
    return _PREFIXO_DE_ESCRITA.sub("", normalizar(item)).strip(" -–—")


def diferenca(anterior: list[dict[str, Any]],
              atual: list[dict[str, Any]]) -> dict[str, Any]:
    """O que mudou de uma versão do roll para a seguinte.

    É a pergunta que se faz toda vez que um roll é atualizado — "o que entrou,
    o que saiu?" — e que hoje se responde comparando dois PDFs lado a lado.
    """
    def por_tipo(blocos):
        fora: dict[str, dict[str, str]] = {}
        for b in blocos:
            alvo = fora.setdefault(b.get("tipo") or "a confirmar", {})
            for item in b.get("itens") or []:
                alvo[_chave(item)] = item
        return fora

    antes, depois = por_tipo(anterior), por_tipo(atual)
    entrou: list[dict[str, str]] = []
    saiu: list[dict[str, str]] = []
    for tipo in sorted(set(antes) | set(depois), key=lambda t: TIPOS.index(t) if t in TIPOS else 9):
        a, d = antes.get(tipo, {}), depois.get(tipo, {})
        entrou += [{"tipo": tipo, "item": d[k]} for k in d if k not in a]
        saiu += [{"tipo": tipo, "item": a[k]} for k in a if k not in d]
    return {
        "entrou": entrou,
        "saiu": saiu,
        "imagens_antes": total_de_imagens(anterior),
        "imagens_depois": total_de_imagens(atual),
    }
