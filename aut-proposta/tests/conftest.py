"""Fixtures compartilhados dos testes de banco."""
from __future__ import annotations

import os

import psycopg
import pytest

from app.db.conexao import get_conn

DSN_TESTE = os.environ.get(
    "DATABASE_URL_TEST", "postgresql://postgres:postgres@localhost:5432/aut_proposta_test"
)

TABELAS = ("proposta_itens", "propostas", "clientes", "preco_item", "preco_categoria")


@pytest.fixture
def db():
    """Conexão ao Postgres de teste, com schema aplicado e tabelas limpas.

    Pula o teste (não falha) se o banco estiver indisponível.
    """
    from app.db.schema import aplicar_schema  # import tardio: existe a partir da Task 2

    try:
        conn = get_conn(DSN_TESTE)
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres de teste indisponível ({e}). Suba com: docker compose up -d db-test")

    aplicar_schema(conn)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABELAS)} RESTART IDENTITY CASCADE")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()
