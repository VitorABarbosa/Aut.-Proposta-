"""Levantamento de orçamento pela tabela padrão (planilha).

Classifica cada descrição, aplica o preço da tabela e formata a descrição no
padrão de escrita do Flying Studio. Soma por categoria e no total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dominio.descontos import Desconto, aplicar_desconto
from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar

CATEGORIAS = ("externas", "internas", "plantas")
PREFIXOS = {
    "externas": "Perspectiva ",
    "internas": "Perspectiva ",
    "plantas": "Planta Humanizada ",
}
_PREFIXOS_JA_ESCRITOS = {
    "externas": ("perspectiva", "estudo de fachada", "estudo cromatic"),
    "internas": ("perspectiva",),
    "plantas": ("planta",),
}


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
    externas: CategoriaOrcada
    internas: CategoriaOrcada
    plantas: CategoriaOrcada

    @property
    def subtotal(self) -> int:
        return self.externas.total + self.internas.total + self.plantas.total

    @property
    def total_imagens(self) -> int:
        return self.externas.qtd + self.internas.qtd + self.plantas.qtd

    def to_dict(self) -> dict[str, Any]:
        return {
            "estrategia": self.estrategia,
            "subtotal": self.subtotal,
            "total_imagens": self.total_imagens,
            "externas": self.externas.to_dict(),
            "internas": self.internas.to_dict(),
            "plantas": self.plantas.to_dict(),
        }


def _formata_descricao(desc_usuario: str, categoria: str) -> str:
    """Aplica o jeito de escrever do Flying Studio.

    Se o usuário já começou com 'Perspectiva'/'Planta'/etc., mantém (só sobe a
    inicial). Senão, prefixa com o padrão da categoria.
    """
    desc = desc_usuario.strip()
    norm = normalizar(desc)
    if any(norm.startswith(p) for p in _PREFIXOS_JA_ESCRITOS.get(categoria, ())):
        return desc[:1].upper() + desc[1:] if desc else desc
    return PREFIXOS[categoria] + desc


def orcar_pela_planilha(
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos | None = None,
) -> Orcamento:
    tabela = tabela or TabelaPrecos()
    cats: dict[str, CategoriaOrcada] = {c: CategoriaOrcada(nome=c) for c in CATEGORIAS}

    for cat in CATEGORIAS:
        for desc in descricoes.get(cat, []):
            classif = tabela.classificar(desc, cat)
            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=_formata_descricao(desc, cat),
                    preco=classif["preco"],
                    fonte=f"planilha:{classif['chave']}",
                )
            )

    return Orcamento(
        estrategia="planilha",
        externas=cats["externas"],
        internas=cats["internas"],
        plantas=cats["plantas"],
    )


def fechar_orcamento(orcamento: Orcamento, desconto: "Desconto | None" = None) -> dict[str, Any]:
    """Junta o orçamento e o cálculo financeiro (com desconto) numa estrutura."""
    return {
        "orcamento": orcamento.to_dict(),
        "financeiro": aplicar_desconto(orcamento.subtotal, desconto),
    }
