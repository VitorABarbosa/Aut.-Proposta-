"""Valida o .docx gerado reabrindo com python-docx e inspecionando o texto."""
import datetime as dt

import pytest
from docx import Document

from app.docx.gerador import gerar_docx

CLIENTE = {"empresa": "GALLI", "ref": "Empreendimento Teste", "contato": "Daniel Pucci"}


def _fechado_galli():
    # Espelho reduzido do caso real GALLI (Plano 1): subtotal 38250, 12% -> 33660.
    return {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 38250, "total_imagens": 3,
            "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                         "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000,
                                    "fonte": "planilha:fachada"}]},
            "internas": {"nome": "internas", "qtd": 1, "total": 1750,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1750,
                                    "fonte": "planilha:interna_diversa"}]},
            "plantas": {"nome": "plantas", "qtd": 1, "total": 33500,
                        "itens": [{"descricao": "Planta Humanizada Tipo", "preco": 33500,
                                   "fonte": "planilha:planta_tipo"}]},
        },
        "financeiro": {"subtotal": 38250, "desconto_pct": 12.0, "desconto_valor": 4590.0,
                       "total": 33660.0, "rotulo": "12% parceria"},
    }


def _texto_completo(path):
    doc = Document(str(path))
    partes = [p.text for p in doc.paragraphs]
    for tab in doc.tables:
        for row in tab.rows:
            for cell in row.cells:
                partes.append(cell.text)
    return "\n".join(partes)


def test_gera_docx_com_conteudo_essencial(tmp_path):
    saida = tmp_path / "proposta.docx"
    resultado = gerar_docx(CLIENTE, _fechado_galli(), saida, data=dt.date(2026, 7, 19))

    assert resultado == saida
    assert saida.exists()
    texto = _texto_completo(saida)

    assert "PROPOSTA COMERCIAL" in texto
    assert "GALLI" in texto
    assert "EMPREENDIMENTO TESTE" in texto
    assert "DANIEL PUCCI" in texto
    assert "R$33.660,00" in texto            # investimento final
    assert "R$38.250,00" in texto            # valor bruto
    assert "12% parceria" in texto           # rótulo do desconto
    assert "Trinta e Três Mil, Seiscentos e Sessenta Reais" in texto
    assert "Perspectiva Fachada" in texto
    assert "Planta Humanizada Tipo" in texto
    assert "19 de Julho de 2026" in texto
    # Seções fixas
    for secao in ("APRESENTAÇÃO", "FORMA DE PAGAMENTO", "PRAZOS DE ENTREGA",
                  "CONSIDERAÇÕES", "ENTREGA FINAL"):
        assert secao in texto


def test_sem_desconto_nao_mostra_valor_bruto(tmp_path):
    fechado = _fechado_galli()
    fechado["financeiro"] = {"subtotal": 38250, "desconto_pct": 0.0,
                             "desconto_valor": 0.0, "total": 38250.0, "rotulo": ""}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "VALOR BRUTO" not in texto
    assert "R$38.250,00" in texto


def test_categoria_vazia_omitida(tmp_path):
    fechado = _fechado_galli()
    fechado["orcamento"]["plantas"] = {"nome": "plantas", "qtd": 0, "total": 0, "itens": []}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "PLANTAS HUMANIZADAS" not in texto


def test_precos_individuais_opcionais(tmp_path):
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, _fechado_galli(), saida, mostra_precos_individuais=True)
    texto = _texto_completo(saida)
    assert "R$3.000,00" in texto  # preço do item aparece na tabela
