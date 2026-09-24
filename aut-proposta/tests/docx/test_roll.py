"""O .docx do roll: a lista de produção, sem preço nenhum."""
import datetime as dt

import pytest
from docx import Document

from app.docx.roll import gerar_roll_docx

CLIENTE = {"empresa": "OUSY", "ref": "Vila Mariana"}
DATA = dt.date(2026, 9, 24)

ROLL = {"aprovado_em": "2026-06-30", "blocos": [
    {"tipo": "externas", "titulo": "", "itens": ["Fachada noturna conceitual", "Piscina"]},
    {"tipo": "internas", "titulo": "", "itens": ["Lobby"]},
    {"tipo": "plantas", "titulo": "", "itens": ["Implantação do pavimento (2º ao 12º)"]},
    {"tipo": "servico", "titulo": "Desenvolvimento de Aplicação Web – Para Web Touch",
     "itens": []},
]}


def _texto(caminho):
    return "\n".join(p.text for p in Document(str(caminho)).paragraphs)


def test_o_roll_sai_no_formato_dos_rolls_reais(tmp_path):
    texto = _texto(gerar_roll_docx(CLIENTE, ROLL, tmp_path / "r.docx",
                                   data=DATA, emissor="flying"))
    assert "OUSY - REF: VILA MARIANA" in texto
    assert "2.1 – Ilustrações Externas" in texto
    assert "1. Fachada noturna conceitual" in texto
    assert "2.2 – Ilustrações Internas" in texto
    assert "2.3 – Plantas Baixas" in texto
    assert "1. Implantação do pavimento (2º ao 12º)" in texto
    assert "Aprovado em: 30 de Junho de 2026." in texto


def test_roll_nao_tem_preco(tmp_path):
    texto = _texto(gerar_roll_docx(CLIENTE, ROLL, tmp_path / "r.docx",
                                   data=DATA, emissor="flying"))
    assert "R$" not in texto
    assert "Valor total" not in texto
    assert "INVESTIMENTO" not in texto.upper()


def test_servico_conhecido_traz_o_escopo_ja_cadastrado(tmp_path):
    """No roll o escopo do serviço É a lista numerada — a mesma que o gerador
    da proposta já escreve embaixo do item."""
    texto = _texto(gerar_roll_docx(CLIENTE, ROLL, tmp_path / "r.docx",
                                   data=DATA, emissor="flying"))
    assert "2.4 – Desenvolvimento de Aplicação Web – Para Web Touch" in texto
    assert "1. Catálogo Digital Interativo" in texto
    assert "8. Revista Digital" in texto


def test_escopo_escrito_no_roll_ganha_do_cadastrado(tmp_path):
    roll = {"blocos": [{"tipo": "servico", "titulo": "Maquete Eletrônica",
                        "itens": ["Só isto", "E mais isto"]}]}
    texto = _texto(gerar_roll_docx(CLIENTE, roll, tmp_path / "r.docx",
                                   data=DATA, emissor="flying"))
    assert "1. Só isto" in texto and "2. E mais isto" in texto


@pytest.mark.parametrize("emissor", ["flying", "rinno", "nid"])
def test_as_tres_empresas_tem_roll(tmp_path, emissor):
    """"não apenas da flying temos roll, atualizamos as vezes o roll da nid e
    da rinno"."""
    texto = _texto(gerar_roll_docx(CLIENTE, ROLL, tmp_path / f"{emissor}.docx",
                                   data=DATA, emissor=emissor))
    assert "OUSY - REF: VILA MARIANA" in texto
    assert "2.1 – Ilustrações Externas" in texto


def test_sem_data_de_aprovacao_vale_a_do_dia(tmp_path):
    roll = {"blocos": [{"tipo": "externas", "titulo": "", "itens": ["Piscina"]}]}
    texto = _texto(gerar_roll_docx(CLIENTE, roll, tmp_path / "r.docx",
                                   data=DATA, emissor="flying"))
    assert "Aprovado em: 24 de Setembro de 2026." in texto
