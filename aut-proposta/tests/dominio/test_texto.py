from app.dominio.texto import normalizar


def test_remove_acento_e_baixa_caixa():
    assert normalizar("Fachada Vista da Calçada") == "fachada vista da calcada"


def test_colapsa_espacos_e_apara():
    assert normalizar("  Planta   Térreo  ") == "planta terreo"


def test_string_vazia():
    assert normalizar("") == ""
