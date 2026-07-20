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


def orcar_pela_planilha(
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos | None = None,
) -> Orcamento:
    tabela = tabela or TabelaPrecos()
    cats: dict[str, CategoriaOrcada] = {
        c: CategoriaOrcada(nome=c, rotulo=tabela.meta(c)["rotulo"]) for c in tabela.categorias()
    }

    for cat in tabela.categorias():
        for desc in descricoes.get(cat, []):
            classif = tabela.classificar(desc, cat)
            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=_formata_descricao(desc, cat, tabela),
                    preco=classif["preco"],
                    fonte=f"planilha:{classif['chave']}",
                )
            )

    return Orcamento(estrategia="planilha", categorias=cats)


def fechar_orcamento(orcamento: Orcamento, desconto: "Desconto | None" = None) -> dict[str, Any]:
    """Junta o orçamento e o cálculo financeiro (com desconto) numa estrutura."""
    return {
        "orcamento": orcamento.to_dict(),
        "financeiro": aplicar_desconto(orcamento.subtotal, desconto),
    }
