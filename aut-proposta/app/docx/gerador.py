"""Porta de entrada da geração do .docx: escolhe a empresa e escreve o corpo.

Cada uma das três empresas do grupo tem o seu próprio documento — não é o
mesmo texto com o logo trocado. Flying vende imagem e tecnologia em três
seções; Rinno vende filme, com o escopo de cada um em bullets; NID vende
projeto, em seis seções com fases EP/PRE/EX e lâminas numeradas. O que é comum
(tipografia, timbrado, cabeçalho, investimento, pagamento, assinatura) está em
`app/docx/base.py`; o que é de cada uma, em `flying.py`, `rinno.py` e `nid.py`.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from app.docx import flying, nid, rinno
from app.docx.base import abrir_documento, timbrado_de
from app.empresas import EMISSOR_PADRAO, empresa

ESCRITORES = {
    "flying": flying.escrever,
    "rinno": rinno.escrever,
    "nid": nid.escrever,
}

# Timbrado da Flying — mantido como nome público porque o resto do projeto e os
# testes antigos se referem a ele.
TIMBRADO_PATH = timbrado_de(empresa(EMISSOR_PADRAO))


def gerar_docx(
    cliente: dict[str, str],
    fechado: dict[str, Any],
    saida: Path,
    data: dt.date | None = None,
    mostra_precos_individuais: bool = False,
    emissor: str | None = None,
) -> Path:
    """Escreve a proposta da empresa `emissor` (default: Flying) em `saida`."""
    emp = empresa(emissor)
    doc = abrir_documento(emp)
    ESCRITORES[emp.chave](
        doc, emp, cliente, fechado, data or dt.date.today(), mostra_precos_individuais
    )
    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida
