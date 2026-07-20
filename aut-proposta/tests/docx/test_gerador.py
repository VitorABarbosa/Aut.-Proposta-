"""Valida o .docx gerado (modelo oficial PROPOSTA_EXEMPLO) reabrindo com python-docx."""
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

    # Cabeçalho no formato do modelo
    assert "PROPOSTA DE IMAGENS, FILMES E TECNOLOGIAS 3D" in texto
    assert "GALLI - REF: EMPREENDIMENTO TESTE" in texto
    assert "A/C: DANIEL PUCCI" in texto
    # Valores (o investimento usa "R$ " com espaço, como no modelo)
    assert "R$ 33.660,00" in texto           # investimento final
    assert "R$38.250,00" in texto            # valor bruto (desconto presente)
    assert "12% parceria" in texto
    assert "Valor total: " in texto
    # Itens numerados
    assert "1. Perspectiva Fachada" in texto
    assert "1. Planta Humanizada Tipo" in texto
    assert "19 de Julho de 2026" in texto
    # Estrutura numerada do modelo oficial
    for trecho in (
        "1  – APRESENTAÇÃO FLYING STUDIO",
        "Nascemos para dar forma ao invisível",
        "2  – ITENS A SEREM DESENVOLVIDOS / INVESTIMENTOS:",
        "2.1 Ilustrações Externas",
        "2.2 Ilustrações Internas",
        "2.3 Plantas Humanizadas 2D",
        "2.4 INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA DESCRITOS:",
        "2.5 FORMA DE PAGAMENTO:",
        "3  – PRAZOS / SOLICITAÇÕES / CONSIDERAÇÕES / ENTREGAS",
        "3.1 Shades",
        "3.2 SOLICITAÇÕES:",
        "3.3 CONSIDERAÇÕES IMAGENS:",
        "3.4 ENTREGA FINAL:",
        "De acordo,",
    ):
        assert trecho in texto


def test_sem_desconto_nao_mostra_valor_bruto(tmp_path):
    fechado = _fechado_galli()
    fechado["financeiro"] = {"subtotal": 38250, "desconto_pct": 0.0,
                             "desconto_valor": 0.0, "total": 38250.0, "rotulo": ""}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "Valor bruto" not in texto
    assert "R$ 38.250,00" in texto


def test_categoria_vazia_omitida_e_renumera(tmp_path):
    fechado = _fechado_galli()
    fechado["orcamento"]["plantas"] = {"nome": "plantas", "qtd": 0, "total": 0, "itens": []}
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)
    assert "Plantas Humanizadas 2D" not in texto
    # Com 2 categorias, investimento e pagamento renumeram para 2.3/2.4.
    assert "2.3 INVESTIMENTO PARA O DESENVOLVIMENTOS" in texto
    assert "2.4 FORMA DE PAGAMENTO:" in texto


def test_categorias_dinamicas_via_categorias_meta(tmp_path):
    """Com `_categorias` do catálogo 2026, seções 2.N seguem a ordem do banco e
    categorias extras (filmes/tecnologia) aparecem com subtítulo próprio,
    renumerando investimento/pagamento."""
    fechado = _fechado_galli()
    orc = fechado["orcamento"]
    orc["filmes"] = {"nome": "filmes", "qtd": 1, "total": 15000,
                      "itens": [{"descricao": "Filme institucional 60 segundos",
                                 "preco": 15000, "fonte": "planilha:filme_3d_60s"}]}
    orc["tecnologia"] = {"nome": "tecnologia", "qtd": 1, "total": 22800,
                          "itens": [{"descricao": "Aplicação Web Touch", "preco": 22800,
                                     "fonte": "planilha:app_web_touch"}]}
    orc["_categorias"] = [
        {"nome": "externas", "rotulo": "Ilustrações Externas"},
        {"nome": "internas", "rotulo": "Ilustrações Internas"},
        {"nome": "plantas", "rotulo": "Plantas Humanizadas 2D"},
        {"nome": "filmes", "rotulo": "Filmes e Takes 3D"},
        {"nome": "tour_virtual", "rotulo": "Tour Virtual / VR 360"},
        {"nome": "drone", "rotulo": "Drone e Fotografia Aérea"},
        {"nome": "estudos", "rotulo": "Estudos de Fachada"},
        {"nome": "tecnologia", "rotulo": "Tecnologias Interativas"},
    ]
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)

    assert "2.1 Ilustrações Externas" in texto
    assert "2.2 Ilustrações Internas" in texto
    assert "2.3 Plantas Humanizadas 2D" in texto
    assert "2.4 Filmes e Takes 3D" in texto
    assert "2.5 Tecnologias Interativas" in texto
    # Categorias sem itens (tour_virtual/drone/estudos) não geram subtítulo.
    assert "Tour Virtual / VR 360" not in texto
    assert "Drone e Fotografia Aérea" not in texto
    assert "Estudos de Fachada" not in texto
    assert "Filme institucional 60 segundos" in texto
    assert "Aplicação Web Touch" in texto
    # Investimento e forma de pagamento renumeram para 2.6/2.7.
    assert "2.6 INVESTIMENTO PARA O DESENVOLVIMENTOS" in texto
    assert "2.7 FORMA DE PAGAMENTO:" in texto


def test_categorias_meta_ausente_usa_fallback_fixo(tmp_path):
    """Propostas antigas re-geradas sem `_categorias` mantêm as 3 categorias fixas
    com os rótulos atuais (comportamento anterior à Task 3)."""
    fechado = _fechado_galli()
    assert "_categorias" not in fechado["orcamento"]
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, fechado, saida)
    texto = _texto_completo(saida)

    assert "2.1 Ilustrações Externas" in texto
    assert "2.2 Ilustrações Internas" in texto
    assert "2.3 Plantas Humanizadas 2D" in texto
    assert "2.4 INVESTIMENTO PARA O DESENVOLVIMENTOS DOS ITENS ACIMA DESCRITOS:" in texto
    assert "2.5 FORMA DE PAGAMENTO:" in texto


def test_destaques_inline_do_modelo(tmp_path):
    """Fidelidade run a run: negritos, itálicos/sublinhados e marca-texto do exemplo."""
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, _fechado_galli(), saida)
    doc = Document(str(saida))

    def runs_de(paragrafo_contendo):
        for p in doc.paragraphs:
            if paragrafo_contendo in p.text:
                return p.runs
        raise AssertionError(f"parágrafo não encontrado: {paragrafo_contendo}")

    # Cliente/REF e A/C: negrito + marca-texto amarelo.
    r = runs_de("GALLI - REF:")[0]
    assert r.bold and r.font.highlight_color is not None

    # NID Studio em negrito dentro do OBS.
    runs = runs_de("NID Studio")
    nid = next(x for x in runs if "NID Studio" in x.text)
    assert nid.bold

    # “R00” em negrito nas considerações; "Shade" em itálico.
    runs = runs_de("Etapas e Tiros de Aprovação")
    assert any("“R00”" in x.text and x.bold for x in runs)
    assert any(x.text == "Shade" and x.italic for x in runs)

    # Citação da apresentação em itálico + sublinhado.
    runs = runs_de("uma imagem vale mais do que mil palavras")
    citacao = next(x for x in runs if "mil palavras" in x.text)
    assert citacao.italic and citacao.underline

    # Frame.io/Adobe e Full HD a 30 FPS em negrito na entrega final.
    runs = runs_de("Resolução das Animações/Filmes")
    assert any("Full HD a 30 FPS" in x.text and x.bold for x in runs)

    # Linha "Valor total:" inteira em negrito.
    runs = runs_de("Valor total:")
    assert all(x.bold for x in runs if x.text.strip())

    # Assinatura: linha centralizada VAZIA (o cliente assina sobre ela no PDF);
    # o nome do cliente NÃO aparece depois da linha.
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    linha = doc.paragraphs[-1]
    assert set(linha.text) == {"_"}  # linha de assinatura, último parágrafo
    assert linha.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert doc.paragraphs[-2].text == "De acordo,"


def test_precos_individuais_opcionais(tmp_path):
    saida = tmp_path / "p.docx"
    gerar_docx(CLIENTE, _fechado_galli(), saida, mostra_precos_individuais=True)
    texto = _texto_completo(saida)
    assert "1. Perspectiva Fachada — R$3.000,00" in texto

    saida2 = tmp_path / "p2.docx"
    gerar_docx(CLIENTE, _fechado_galli(), saida2, mostra_precos_individuais=False)
    texto2 = _texto_completo(saida2)
    assert "— R$3.000,00" not in texto2  # sem preço por item; só o Valor total
