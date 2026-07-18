import pytest

from app.dominio.descontos import Desconto, aplicar_desconto


def test_sem_desconto():
    r = aplicar_desconto(10000, None)
    assert r["desconto_valor"] == 0
    assert r["total"] == 10000


def test_desconto_percentual():
    r = aplicar_desconto(23450, Desconto("percentual", 12, "12% Parceria"))
    assert r["desconto_valor"] == 2814.0
    assert r["total"] == 20636.0
    assert r["desconto_pct"] == 12
    assert r["rotulo"] == "12% Parceria"


def test_desconto_valor_fixo():
    r = aplicar_desconto(10000, Desconto("valor", 1500))
    assert r["desconto_valor"] == 1500
    assert r["total"] == 8500


def test_desconto_nao_deixa_total_negativo():
    r = aplicar_desconto(1000, Desconto("valor", 5000))
    assert r["total"] == 0


def test_tipo_invalido_levanta_erro():
    with pytest.raises(ValueError):
        aplicar_desconto(1000, Desconto("bonus", 10))
