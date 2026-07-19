import os

import psycopg
import pytest

from app.db.conexao import get_conn

DSN_TESTE = os.environ.get(
    "DATABASE_URL_TEST", "postgresql://postgres:postgres@localhost:5432/aut_proposta_test"
)


def test_get_conn_usa_dsn_explicito():
    try:
        conn = get_conn(DSN_TESTE)
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres de teste indisponível ({e}). Suba com: docker compose up -d db-test")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()
