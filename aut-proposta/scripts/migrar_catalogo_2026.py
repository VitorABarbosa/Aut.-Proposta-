"""Migração do catálogo 2026 (schema + reseed) — roda contra NEON prod.

Idempotente: pode ser executado quantas vezes forem necessárias sem duplicar
dados nem levantar erro. Reaplica `app/db/schema.sql` (que já cobre tanto um
banco zerado quanto um banco com o schema anterior — 3 categorias fixas, sem
`tabela`, PK simples em `categoria`) e depois re-semeia `preco_categoria` e
`preco_item` a partir de `app/dados/precos_2026.json` (tabelas padrao+mcmv).

Dados de `clientes`/`propostas`/`proposta_itens` são preservados (a migração
é ALTER, não DROP); só `preco_*` é re-semeado (TRUNCATE + INSERT).

Uso: defina DATABASE_URL e rode `python -m scripts.migrar_catalogo_2026`.
"""
from __future__ import annotations

import psycopg

from app.db.conexao import get_conn
from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos


def migrar(conn: psycopg.Connection) -> dict[str, int]:
    aplicar_schema(conn)  # ALTER TABLE ... ADD COLUMN IF NOT EXISTS + recria PK/FK/UNIQUE compostas
    contagens = semear_precos(conn)
    conn.commit()
    return contagens


if __name__ == "__main__":
    conn = get_conn()
    try:
        print(migrar(conn))
    finally:
        conn.close()
