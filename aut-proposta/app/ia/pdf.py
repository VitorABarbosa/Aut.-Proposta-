"""Texto de um PDF — o roll chega assim, exportado do Word.

Roll é documento de texto: dá para ler sem gastar visão. Quando o PDF vier
escaneado (sem camada de texto), sai vazio e quem chamou manda pela visão,
como um print.
"""
from __future__ import annotations

import io

LIMITE_PAGINAS = 30


def texto_do_pdf(dados: bytes) -> str:
    """Todas as páginas, na ordem, separadas por linha em branco."""
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(dados))
    paginas = [(p.extract_text() or "").strip() for p in leitor.pages[:LIMITE_PAGINAS]]
    return "\n\n".join(p for p in paginas if p)
