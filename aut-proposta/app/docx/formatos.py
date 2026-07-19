"""Formatação de valores monetários, extenso e datas em português."""
from __future__ import annotations

import datetime as dt

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_UNIDADES = ["", "Um", "Dois", "Três", "Quatro", "Cinco", "Seis", "Sete", "Oito", "Nove",
             "Dez", "Onze", "Doze", "Treze", "Quatorze", "Quinze", "Dezesseis", "Dezessete",
             "Dezoito", "Dezenove"]
_DEZENAS = ["", "", "Vinte", "Trinta", "Quarenta", "Cinquenta", "Sessenta", "Setenta",
            "Oitenta", "Noventa"]
_CENTENAS = ["", "Cento", "Duzentos", "Trezentos", "Quatrocentos", "Quinhentos",
             "Seiscentos", "Setecentos", "Oitocentos", "Novecentos"]


def brl(valor: float) -> str:
    s = f"{valor:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R${s}"


def data_extenso(data: dt.date) -> str:
    return f"{data.day:02d} de {MESES_PT[data.month - 1]} de {data.year}"


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "Cem"
    partes: list[str] = []
    c, r = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if r < 20:
        if r:
            partes.append(_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        if u:
            partes.append(f"{_DEZENAS[d]} e {_UNIDADES[u]}")
        else:
            partes.append(_DEZENAS[d])
    return " e ".join(partes)


def extenso(valor: float) -> str:
    inteiro = int(round(valor))
    if inteiro == 0:
        return "Zero Reais"

    milhoes, resto = divmod(inteiro, 1_000_000)
    milhares, unidades = divmod(resto, 1_000)

    blocos: list[str] = []
    if milhoes:
        blocos.append(f"{_ate_999(milhoes)} {'Milhão' if milhoes == 1 else 'Milhões'}")
    if milhares:
        blocos.append("Mil" if milhares == 1 else f"{_ate_999(milhares)} Mil")
    if unidades:
        blocos.append(_ate_999(unidades))

    texto = ", ".join(blocos) if len(blocos) > 1 else blocos[0]
    return f"{texto} {'Real' if inteiro == 1 else 'Reais'}"
