"""Conexão com o Postgres (NEON em produção, Postgres local em teste)."""
from __future__ import annotations

import os

import psycopg


def get_conn(dsn: str | None = None) -> psycopg.Connection:
    """Abre uma conexão. Se dsn=None, usa a variável DATABASE_URL."""
    dsn = dsn or os.environ["DATABASE_URL"]
    return psycopg.connect(dsn)
