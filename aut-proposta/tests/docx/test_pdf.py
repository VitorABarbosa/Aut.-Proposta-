import shutil

import pytest

from app.docx.pdf import converter_para_pdf

tem_soffice = bool(shutil.which("soffice") or shutil.which("libreoffice"))


@pytest.mark.skipif(not tem_soffice, reason="LibreOffice (soffice) não instalado — validado no Docker")
def test_converte_docx_gerado_para_pdf(tmp_path):
    import datetime as dt
    from app.docx.gerador import gerar_docx

    cliente = {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"}
    fechado = {
        "orcamento": {"estrategia": "planilha", "subtotal": 3000, "total_imagens": 1,
                      "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                                   "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000, "fonte": "planilha"}]},
                      "internas": {"nome": "internas", "qtd": 0, "total": 0, "itens": []},
                      "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []}},
        "financeiro": {"subtotal": 3000, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 3000.0, "rotulo": ""},
    }
    docx = tmp_path / "p.docx"
    gerar_docx(cliente, fechado, docx, data=dt.date(2026, 7, 19))
    pdf = converter_para_pdf(docx)
    assert pdf is not None and pdf.exists()
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_sem_soffice_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nome: None)
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    assert converter_para_pdf(arq) is None


def test_falha_do_soffice_devolve_none(tmp_path, monkeypatch):
    import subprocess as sp

    monkeypatch.setattr("shutil.which", lambda nome: "C:/fake/soffice")

    def _explode(*a, **kw):
        raise sp.CalledProcessError(1, "soffice")

    monkeypatch.setattr("subprocess.run", _explode)
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    assert converter_para_pdf(arq) is None
