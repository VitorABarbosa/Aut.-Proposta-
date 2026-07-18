"""Aplicação de descontos sobre o subtotal de um orçamento.

Suporta desconto percentual (0-100) e valor fixo em reais. O cálculo é
determinístico e nunca deixa o total ficar negativo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TIPOS_VALIDOS = ("percentual", "valor")


@dataclass
class Desconto:
    tipo: str
    valor: float
    rotulo: str = ""


def aplicar_desconto(subtotal: int, desconto: Desconto | None) -> dict[str, Any]:
    if desconto is None:
        return {
            "subtotal": subtotal,
            "desconto_pct": 0.0,
            "desconto_valor": 0.0,
            "total": float(subtotal),
            "rotulo": "",
        }

    if desconto.tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo de desconto inválido: {desconto.tipo}")

    if desconto.tipo == "percentual":
        desconto_pct = float(desconto.valor)
        desconto_valor = subtotal * (desconto_pct / 100.0)
    else:  # valor
        desconto_valor = float(desconto.valor)
        desconto_pct = (desconto_valor / subtotal * 100.0) if subtotal else 0.0

    total = max(0.0, subtotal - desconto_valor)

    return {
        "subtotal": subtotal,
        "desconto_pct": round(desconto_pct, 2),
        "desconto_valor": round(desconto_valor, 2),
        "total": round(total, 2),
        "rotulo": desconto.rotulo,
    }
