"""Upload do .docx no Cloudflare R2 (API compatível com S3, via boto3).

Degradação graciosa: sem credenciais ou com upload falhando, devolve None e o
chamador segue oferecendo o download direto pela API (decisão do design, §7).
"""
from __future__ import annotations

import os
from pathlib import Path

_ENVS_OBRIGATORIAS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def r2_configurado() -> bool:
    return all(os.getenv(k) for k in _ENVS_OBRIGATORIAS)


def _cliente_s3():
    import boto3

    conta = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{conta}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def enviar_docx(caminho: Path, chave: str) -> str | None:
    """Sobe o arquivo e devolve a URL pública, ou None se não der (nunca levanta)."""
    if not r2_configurado():
        return None
    try:
        s3 = _cliente_s3()
        s3.upload_file(
            Filename=str(caminho),
            Bucket=os.environ["R2_BUCKET"],
            Key=chave,
            ExtraArgs={"ContentType": MIME_DOCX},
        )
    except Exception:  # noqa: BLE001 — falha de upload nunca derruba a geração
        return None

    base = os.getenv("R2_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{chave}"
    conta = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    return f"https://{conta}.r2.cloudflarestorage.com/{bucket}/{chave}"


def excluir_objetos(chaves: list[str]) -> int:
    """Apaga objetos do bucket. Nunca levanta; sem credenciais devolve 0."""
    if not r2_configurado() or not chaves:
        return 0
    try:
        s3 = _cliente_s3()
        bucket = os.environ["R2_BUCKET"]
        n = 0
        for chave in chaves:
            s3.delete_object(Bucket=bucket, Key=chave)
            n += 1
        return n
    except Exception:  # noqa: BLE001 — falha de exclusão nunca levanta
        return 0
