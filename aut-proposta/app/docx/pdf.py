"""Conversão docx -> pdf via LibreOffice headless (instalado no Docker)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def converter_para_pdf(docx: Path) -> Path | None:
    """Converte no mesmo diretório. None se o LibreOffice não está instalado."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", str(docx.parent), str(docx)],
        check=True, capture_output=True, timeout=120,
    )
    pdf = docx.with_suffix(".pdf")
    return pdf if pdf.exists() else None
