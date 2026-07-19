"""Conversão docx -> pdf via LibreOffice headless (instalado no Docker)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def converter_para_pdf(docx: Path) -> Path | None:
    """Converte no mesmo diretório. None se o LibreOffice não está instalado
    ou se a conversão falhar/estourar o tempo (o chamador responde com erro claro)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    # Perfil de usuário isolado por invocação: o perfil default do LibreOffice
    # não suporta conversões concorrentes em modo headless.
    with tempfile.TemporaryDirectory() as perfil:
        try:
            subprocess.run(
                [soffice, "--headless",
                 f"-env:UserInstallation=file:///{Path(perfil).as_posix()}",
                 "--convert-to", "pdf",
                 "--outdir", str(docx.parent), str(docx)],
                check=True, capture_output=True, timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    pdf = docx.with_suffix(".pdf")
    return pdf if pdf.exists() else None
