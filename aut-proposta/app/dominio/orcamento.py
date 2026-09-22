"""Levantamento de orçamento pela tabela padrão (planilha).

Classifica cada descrição, aplica o preço da tabela e formata a descrição no
padrão de escrita do Flying Studio. Soma por categoria e no total. As
categorias são dinâmicas — vêm de `TabelaPrecos.categorias()` (NEON), na
ordem de `ordem` do catálogo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dominio.descontos import Desconto, aplicar_desconto
from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar

# Fallback só para compat de leitura antiga (sem conn/tabela disponível).
CATEGORIAS_FALLBACK = ("externas", "internas", "plantas")

# Categorias cujos itens do catálogo são ETAPAS do mesmo serviço, cada uma
# cobrada POR AMBIENTE. No tour virtual as três linhas (elaboração, render,
# web/mobile) valem para cada área de lazer: 7 áreas custam 7x cada etapa, e é
# assim que as propostas saem ("Vista Virtual Web – Áreas de Lazer (7
# ambientes)"). Diferente do projeto de interiores da NID, onde cada ambiente é
# uma entrada da lista ("Piscina", "Academia") e a conta sai pela quantidade de
# entradas — por isso a regra é por categoria, e não pela palavra "ambiente".
CATEGORIAS_POR_AMBIENTE = ("tour_virtual",)


def e_categoria_por_ambiente(categoria: str) -> bool:
    return categoria in CATEGORIAS_POR_AMBIENTE


@dataclass
class ItemOrcado:
    descricao: str
    descricao_normalizada: str
    preco: int
    fonte: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "descricao": self.descricao_normalizada,
            "preco": self.preco,
            "fonte": self.fonte,
        }


@dataclass
class CategoriaOrcada:
    nome: str
    rotulo: str = ""
    itens: list[ItemOrcado] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(i.preco for i in self.itens)

    @property
    def qtd(self) -> int:
        return len(self.itens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "qtd": self.qtd,
            "total": self.total,
            "itens": [i.to_dict() for i in self.itens],
        }


@dataclass
class Orcamento:
    estrategia: str
    categorias: dict[str, CategoriaOrcada] = field(default_factory=dict)
    # Quantidade de áreas do empreendimento, para as categorias cobradas por
    # ambiente. Vai no dicionário porque o gerador do .docx precisa dela no
    # título ("Vista Virtual Web – Áreas de Lazer (7 ambientes)").
    ambientes: int = 1

    @property
    def subtotal(self) -> int:
        return sum(cat.total for cat in self.categorias.values())

    @property
    def total_imagens(self) -> int:
        return sum(cat.qtd for cat in self.categorias.values())

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "estrategia": self.estrategia,
            "subtotal": self.subtotal,
            "total_imagens": self.total_imagens,
            "ambientes": self.ambientes,
        }
        for nome, cat in self.categorias.items():
            out[nome] = cat.to_dict()
        out["_categorias"] = [
            {"nome": nome, "rotulo": cat.rotulo} for nome, cat in self.categorias.items()
        ]
        return out


def _formata_descricao(desc_usuario: str, categoria: str, tabela: TabelaPrecos) -> str:
    """Aplica o jeito de escrever do Flying Studio.

    Se o usuário já começou com a 1ª palavra do prefixo da categoria (ex.:
    'Perspectiva', 'Planta'), mantém (só sobe a inicial). Senão, prefixa com
    o prefixo do catálogo (`tabela.meta(categoria)["prefixo"]`; "" se a
    categoria não tiver prefixo).
    """
    desc = desc_usuario.strip()
    norm = normalizar(desc)
    prefixo = tabela.meta(categoria)["prefixo"]
    primeira_palavra = normalizar(prefixo).split()[0] if prefixo.strip() else None
    if primeira_palavra and norm.startswith(primeira_palavra):
        return desc[:1].upper() + desc[1:] if desc else desc
    return prefixo + desc


def descricao_final(desc_usuario: str, categoria: str, tabela: TabelaPrecos,
                    descricao_do_catalogo: str, casou: bool = True) -> str:
    """Como o item vai aparecer escrito na proposta.

    Categoria COM prefixo de escrita é imagem: cada cena é diferente ("Fachada
    vista da calçada"), então o texto do usuário é preservado com o prefixo.
    Categoria SEM prefixo é serviço de catálogo — filme, tour, projeto de
    interiores: o nome do serviço é o do catálogo, e não como o usuário
    escreveu na pressa ("filme corretor" vira "Filme Corretor / Produto de até
    1:30"). É o que garante que a proposta saia com o nome comercial certo.
    """
    # Só troca pelo nome comercial o item que casou com uma linha do catálogo.
    # Sem isso, um pedido específico vira o nome do serviço mais parecido.
    if (casou and not e_categoria_de_imagem(categoria, tabela)
            and _descricao_e_so_o_nome(desc_usuario)):
        return descricao_do_catalogo
    desc = desc_usuario.strip()
    return desc[:1].upper() + desc[1:] if not e_categoria_de_imagem(categoria, tabela) else \
        _formata_descricao(desc_usuario, categoria, tabela)


def e_categoria_de_imagem(categoria: str, tabela: TabelaPrecos) -> bool:
    """Categoria com prefixo de escrita ("Perspectiva ", "Planta Humanizada ")
    é imagem: cada unidade é uma cena. Sem prefixo é serviço (filme, tour,
    projeto)."""
    return bool(tabela.meta(categoria)["prefixo"].strip())


def _descricao_e_so_o_nome(desc: str) -> bool:
    """"Filme corretor" é só o nome do serviço e ganha a redação do catálogo.
    "Filme institucional de até 2:00" já traz a duração fechada com o cliente —
    a Turtitta foi vendida assim, e a linha do catálogo diz 3:30 — então fica
    como foi escrito. O critério: até quatro palavras e nenhum número."""
    norm = normalizar(desc)
    return len(norm.split()) <= 4 and not any(c.isdigit() for c in norm)


def entrada_de_item(entrada: Any) -> tuple[str, int | None]:
    """Um item da estrutura pode ser só a descrição ("Filme institucional de
    2:00") ou {descricao, preco} quando a pessoa fechou o valor daquele item
    ("institucional de 2 minutos por 15 mil"). Filme tem muitas variáveis —
    duração, locução, 4K — e a tabela é uma referência por tipo, não a
    regra; o número vem de quem negociou, nunca da IA.

    Devolve (descricao, preco_informado ou None)."""
    if isinstance(entrada, dict):
        desc = str(entrada.get("descricao") or entrada.get("desc") or "").strip()
        preco = entrada.get("preco")
        try:
            preco_int = int(round(float(preco))) if preco not in (None, "") else None
        except (TypeError, ValueError):
            preco_int = None
        if preco_int is not None and preco_int < 0:
            raise ValueError(f"preço informado inválido para '{desc}': {preco}")
        return desc, preco_int
    return str(entrada).strip(), None


def preco_final(preco_catalogo: int, chave: str, categoria: str, tabela: TabelaPrecos,
                ajuste_pct: float = 0.0, preco_por_imagem: int | None = None,
                preco_informado: int | None = None, ambientes: int = 1) -> tuple[int, str]:
    """Preço de um item e a fonte que explica de onde ele saiu.

    Duas práticas da casa que a planilha sozinha não expressa:
    - preço fixo por imagem: o cliente fecha "R$ 2.400 a imagem" e todas as
      perspectivas e plantas saem por isso, seja fachada ou voo de pássaro
      (OUSY a 2.200, UNICOS a 2.400). Só vale para categoria de imagem.
    - ajuste sobre a planilha: cliente novo costuma ser "planilha + 10%";
      negociação pode ser "planilha - 5%". Entra no preço do item, e por isso
      não aparece na proposta — diferente do desconto, que é linha visível.
    - `ambientes`: no tour virtual o preço é proporcional à quantidade de áreas
      do empreendimento (7 áreas de lazer = 7x cada etapa). Multiplica o preço
      de TABELA; preço informado pela pessoa fica como está, porque quem diz
      "a vista virtual por 25 mil" está fechando a linha inteira, não a unidade.
    """
    # O mais específico ganha: preço fechado deste item > preço por imagem >
    # ajuste sobre a tabela > tabela.
    if preco_informado is not None:
        return preco_informado, "informado"
    if preco_por_imagem is not None and e_categoria_de_imagem(categoria, tabela):
        return int(preco_por_imagem), "fixo_por_imagem"

    # Serviço cadastrado sem preço de tabela ("Projeto Executivo Arquitetônico"):
    # entra na proposta e o valor vai à mão depois. A tabela é base, e serviço
    # sem preço não pode impedir a proposta de existir.
    if not preco_catalogo:
        return 0, f"a_definir:{chave}"

    # Serviço que o catálogo NÃO reconhece também entra sem preço. O default da
    # categoria serve para imagem, onde uma cena é uma cena e todas custam o
    # mesmo; em serviço ele é chute com cara de tabela — "Desenvolvimento do
    # Ant. Projeto de 3 Decorados" saía a R$ 2.500, o preço de área comum por
    # ambiente. Pedido específico é assim: entra com o texto de quem pediu, e o
    # valor se valida depois.
    if chave == "default" and not e_categoria_de_imagem(categoria, tabela):
        return 0, "a_definir:default"

    vezes = ambientes if e_categoria_por_ambiente(categoria) and ambientes > 1 else 1
    sufixo = f" x{vezes} ambientes" if vezes > 1 else ""
    if ajuste_pct:
        sinal = "+" if ajuste_pct > 0 else ""
        preco = int(round(preco_catalogo * (1 + ajuste_pct / 100.0))) * vezes
        return preco, f"planilha{sinal}{ajuste_pct:g}%:{chave}{sufixo}"
    return preco_catalogo * vezes, f"planilha:{chave}{sufixo}"


def orcar_pela_planilha(
    descricoes: dict[str, list[Any]],
    tabela: TabelaPrecos | None = None,
    ajuste_pct: float = 0.0,
    preco_por_imagem: int | None = None,
    ambientes: int = 1,
) -> Orcamento:
    tabela = tabela or TabelaPrecos()
    cats: dict[str, CategoriaOrcada] = {
        c: CategoriaOrcada(nome=c, rotulo=tabela.meta(c)["rotulo"]) for c in tabela.categorias()
    }

    for cat in tabela.categorias():
        for entrada in descricoes.get(cat, []):
            desc, informado = entrada_de_item(entrada)
            if not desc:
                continue
            classif = tabela.classificar(desc, cat)
            preco, fonte = preco_final(classif["preco"], classif["chave"], cat, tabela,
                                       ajuste_pct, preco_por_imagem, informado, ambientes)
            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=descricao_final(
                        desc, cat, tabela, classif["descricao_padrao"],
                        casou=classif["chave"] != "default"),
                    preco=preco,
                    fonte=fonte,
                )
            )

    return Orcamento(estrategia="planilha", categorias=cats, ambientes=max(1, ambientes))


def fechar_orcamento(orcamento: Orcamento, desconto: "Desconto | None" = None) -> dict[str, Any]:
    """Junta o orçamento e o cálculo financeiro (com desconto) numa estrutura."""
    return {
        "orcamento": orcamento.to_dict(),
        "financeiro": aplicar_desconto(orcamento.subtotal, desconto),
    }
