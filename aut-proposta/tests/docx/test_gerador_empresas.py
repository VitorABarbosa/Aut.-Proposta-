"""O .docx de cada empresa: estrutura própria, timbrado próprio, arte inteira."""
import datetime as dt

import pytest
from docx import Document

from app.docx.gerador import gerar_docx
from app.empresas import EMISSORES, empresa

CLIENTE = {"empresa": "OUSY", "ref": "Vila Mariana", "contato": "Yuri"}
DATA = dt.date(2026, 9, 11)


def _fechado(categorias: list[tuple[str, str, list[tuple[str, int]]]]):
    """Monta o shape de fechar_orcamento a partir de (nome, rótulo, itens)."""
    orc = {"estrategia": "planilha", "subtotal": 0, "total_imagens": 0,
           "_categorias": [{"nome": n, "rotulo": r} for n, r, _ in categorias]}
    for nome, _rotulo, itens in categorias:
        orc[nome] = {
            "nome": nome, "qtd": len(itens), "total": sum(p for _, p in itens),
            "itens": [{"descricao": d, "preco": p, "fonte": "planilha:x"} for d, p in itens],
        }
        orc["subtotal"] += orc[nome]["total"]
        orc["total_imagens"] += orc[nome]["qtd"]
    return {
        "orcamento": orc,
        "financeiro": {"subtotal": orc["subtotal"], "desconto_pct": 0.0,
                       "desconto_valor": 0.0, "total": float(orc["subtotal"]), "rotulo": ""},
    }


FECHADO_RINNO = _fechado([
    ("rinno_filmes", "Filmes", [
        ("Filme Conceito de até 2:30 (Dois Minutos e Meio)", 14000),
        ("Filme Corretor / Produto de até 1:30 (Um Minuto e Meio)", 10000),
    ]),
    ("rinno_takes", "Takes Animados", [("Take I.A. Animado de até 12 segundos", 650)]),
])

FECHADO_NID = _fechado([
    ("nid_fachada", "Design de Fachada", [("Design de Fachada", 22000)]),
    ("nid_interiores", "Projetos de Interiores", [
        ("Projeto de Interiores — Apto Modelo Decorado (3 dormitórios)", 20000),
        ("Projeto de Interiores — Áreas Comuns / Lazer (por ambiente)", 2500),
    ]),
])

FECHADO_FLYING = _fechado([
    ("externas", "Ilustrações Externas", [("Perspectiva Fachada", 3000)]),
])


def _texto(path):
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


@pytest.mark.parametrize("emissor,fechado", [
    ("flying", FECHADO_FLYING), ("rinno", FECHADO_RINNO), ("nid", FECHADO_NID),
])
def test_cada_empresa_abre_com_o_seu_titulo(tmp_path, emissor, fechado):
    saida = gerar_docx(CLIENTE, fechado, tmp_path / f"{emissor}.docx",
                       data=DATA, emissor=emissor)
    texto = _texto(saida)
    assert texto.startswith(empresa(emissor).titulo_proposta)
    assert "OUSY - REF: VILA MARIANA" in texto
    assert "A/C: YURI" in texto


def test_rinno_traz_o_escopo_de_cada_filme(tmp_path):
    saida = gerar_docx(CLIENTE, FECHADO_RINNO, tmp_path / "r.docx",
                       data=DATA, emissor="rinno")
    texto = _texto(saida)

    assert "1  – APRESENTAÇÃO RINNO FILMS: NASCE O CINEMA IMOBILIÁRIO." in texto
    # Itens numerados um a um, com o escopo logo abaixo.
    assert "2.1 Filme Conceito de até 2:30 (Dois Minutos e Meio)" in texto
    assert "2.2 Filme Corretor / Produto de até 1:30 (Um Minuto e Meio)" in texto
    assert texto.count("Este item inclui:") == 2
    assert "Takes animados para redes sociais e mobile" in texto  # escopo do conceito
    assert "Estrutura: Filme corretor." in texto                  # escopo do produto
    # Take não tem escopo cadastrado: sai só a linha, sem herdar o de filme.
    assert "2.3 Take I.A. Animado de até 12 segundos" in texto
    # Investimento e pagamento em seção própria, como no modelo da Rinno.
    assert "3.1 INVESTIMENTO" in texto and "3.2 FORMA DE PAGAMENTO:" in texto
    assert "4  – PRAZOS / CRONOGRAMAS:" in texto


def test_nid_traz_fases_laminas_e_servicos_adicionais(tmp_path):
    saida = gerar_docx(CLIENTE, FECHADO_NID, tmp_path / "n.docx", data=DATA, emissor="nid")
    texto = _texto(saida)

    assert "1  – APRESENTAÇÃO NID STUDIO" in texto
    assert "2.1 Escopo Contratado:" in texto
    for fase in ("3.1 Estudo Preliminar (EP)", "3.2 Projeto Pré-Executivo (PRE)",
                 "3.3 Projeto Executivo (EX)"):
        assert fase in texto
    assert "Lâmina 01: Análise Consultiva e Moodboard" in texto
    assert "Lâmina 13: Caderno de Especificações Final" in texto
    assert "4  – CRONOGRAMA DE ENTREGAS" in texto
    assert "5.3 SERVIÇOS ADICIONAIS" in texto
    assert "6  – CONSIDERAÇÕES GERAIS E RESPONSABILIDADES" in texto
    assert "6.15 Exclusividade Crítica por Tipologia de Escopo:" in texto


def test_nid_tem_uma_hora_tecnica_so(tmp_path):
    """No modelo em Word ela aparecia como R$ 600,00 no investimento e
    R$ 300,00/h nas considerações — o cliente atento usa a menor."""
    saida = gerar_docx(CLIENTE, FECHADO_NID, tmp_path / "n.docx", data=DATA, emissor="nid")
    texto = _texto(saida)
    assert "R$600,00" in texto
    assert "R$300,00" not in texto
    assert "hora técnica prevista no item 5.3" in texto
    # E a taxa de acompanhamento é citada no item em que de fato está.
    assert "prevista no item 5.3" in texto and "prevista no Item 4" not in texto


def test_pagamento_e_conta_feita_no_codigo(tmp_path):
    """O percentual é da empresa; o valor da parcela nunca é texto digitado."""
    saida = gerar_docx(CLIENTE, FECHADO_NID, tmp_path / "n.docx", data=DATA, emissor="nid")
    texto = _texto(saida)
    total = FECHADO_NID["financeiro"]["total"]  # 44.500,00
    assert "50% – Na aprovação desta Proposta (R$22.250,00)" in texto
    assert "25% – Aprovação do Estudo Preliminar (EP) (R$11.125,00)" in texto
    assert total == 44500.0


@pytest.mark.parametrize("emissor", EMISSORES)
def test_timbrado_sobrevive_com_a_arte_inteira(tmp_path, emissor):
    """O corpo é trocado, mas cabeçalho e rodapé (a arte) ficam — e com a
    largura da página, senão o logo da direita é cortado."""
    fechado = {"flying": FECHADO_FLYING, "rinno": FECHADO_RINNO, "nid": FECHADO_NID}[emissor]
    saida = gerar_docx(CLIENTE, fechado, tmp_path / f"{emissor}.docx",
                       data=DATA, emissor=emissor)
    doc = Document(str(saida))
    secao = doc.sections[0]

    blip = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    assert secao.header.part.element.findall(f".//{blip}"), "cabeçalho perdeu a arte"
    assert secao.footer.part.element.findall(f".//{blip}"), "rodapé perdeu a arte"

    for parte in (secao.header, secao.footer):
        for p in parte.paragraphs:
            assert p.paragraph_format.left_indent == -secao.left_margin
            assert p.paragraph_format.right_indent == -secao.right_margin

    # Word guarda margem em twips, então a volta não bate no EMU exato.
    m = empresa(emissor).margens
    assert round(secao.left_margin.cm, 2) == m.esquerda
    assert round(secao.right_margin.cm, 2) == m.direita


def test_emissor_invalido_nao_gera_documento(tmp_path):
    with pytest.raises(ValueError, match="emissor inválido"):
        gerar_docx(CLIENTE, FECHADO_FLYING, tmp_path / "x.docx", emissor="disney")
