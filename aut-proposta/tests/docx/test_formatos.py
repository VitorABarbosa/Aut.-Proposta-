import datetime as dt

from app.docx.formatos import brl, data_extenso, extenso


def test_brl_milhares():
    assert brl(3660.0) == "R$3.660,00"
    assert brl(33660.0) == "R$33.660,00"
    assert brl(1234567.89) == "R$1.234.567,89"


def test_brl_pequeno():
    assert brl(0) == "R$0,00"
    assert brl(950) == "R$950,00"


def test_extenso_casos_reais():
    # Caso GALLI do Plano 1: total 33660.
    assert extenso(33660) == "Trinta e Três Mil, Seiscentos e Sessenta Reais"
    assert extenso(1) == "Um Real"
    assert extenso(0) == "Zero Reais"
    assert extenso(100) == "Cem Reais"
    assert extenso(1000) == "Mil Reais"
    assert extenso(2_000_000) == "Dois Milhões Reais"


def test_data_extenso():
    assert data_extenso(dt.date(2026, 7, 19)) == "19 de Julho de 2026"
