"""Aplicação idempotente do schema do banco."""
from __future__ import annotations

from pathlib import Path

import psycopg

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def aplicar_schema(conn: psycopg.Connection) -> None:
    """Executa o DDL (CREATE TABLE IF NOT EXISTS ...) e faz commit."""
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
