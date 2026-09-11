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
                    descricao_do_catalogo: str) -> str:
    """Como o item vai aparecer escrito na proposta.

    Categoria COM prefixo de escrita é imagem: cada cena é diferente ("Fachada
    vista da calçada"), então o texto do usuário é preservado com o prefixo.
    Categoria SEM prefixo é serviço de catálogo — filme, tour, projeto de
    interiores: o nome do serviço é o do catálogo, e não como o usuário
    escreveu na pressa ("filme corretor" vira "Filme Corretor / Produto de até
    1:30"). É o que garante que a proposta saia com o nome comercial certo.
    """
    if not e_categoria_de_imagem(categoria, tabela) and _descricao_e_so_o_nome(desc_usuario):
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


def preco_final(preco_catalogo: int, chave: str, categoria: str, tabela: TabelaPrecos,
                ajuste_pct: float = 0.0, preco_por_imagem: int | None = None) -> tuple[int, str]:
    """Preço de um item e a fonte que explica de onde ele saiu.

    Duas práticas da casa que a planilha sozinha não expressa:
    - preço fixo por imagem: o cliente fecha "R$ 2.400 a imagem" e todas as
      perspectivas e plantas saem por isso, seja fachada ou voo de pássaro
      (OUSY a 2.200, UNICOS a 2.400). Só vale para categoria de imagem.
    - ajuste sobre a planilha: cliente novo costuma ser "planilha + 10%";
      negociação pode ser "planilha - 5%". Entra no preço do item, e por isso
      não aparece na proposta — diferente do desconto, que é linha visível.
    """
    if preco_por_imagem is not None and e_categoria_de_imagem(categoria, tabela):
        return int(preco_por_imagem), "fixo_por_imagem"
    if ajuste_pct:
        sinal = "+" if ajuste_pct > 0 else ""
        return int(round(preco_catalogo * (1 + ajuste_pct / 100.0))), f"planilha{sinal}{ajuste_pct:g}%:{chave}"
    return preco_catalogo, f"planilha:{chave}"


def orcar_pela_planilha(
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos | None = None,
    ajuste_pct: float = 0.0,
    preco_por_imagem: int | None = None,
) -> Orcamento:
    tabela = tabela or TabelaPrecos()
    cats: dict[str, CategoriaOrcada] = {
        c: CategoriaOrcada(nome=c, rotulo=tabela.meta(c)["rotulo"]) for c in tabela.categorias()
    }

    for cat in tabela.categorias():
        for desc in descricoes.get(cat, []):
            classif = tabela.classificar(desc, cat)
            preco, fonte = preco_final(classif["preco"], classif["chave"], cat, tabela,
                                       ajuste_pct, preco_por_imagem)
            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=descricao_final(
                        desc, cat, tabela, classif["descricao_padrao"]),
                    preco=preco,
                    fonte=fonte,
                )
            )

    return Orcamento(estrategia="planilha", categorias=cats)


def fechar_orcamento(orcamento: Orcamento, desconto: "Desconto | None" = None) -> dict[str, Any]:
    """Junta o orçamento e o cálculo financeiro (com desconto) numa estrutura."""
    return {
        "orcamento": orcamento.to_dict(),
        "financeiro": aplicar_desconto(orcamento.subtotal, desconto),
    }
