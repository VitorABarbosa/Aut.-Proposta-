"""Semeia a tabela de preços no banco a partir do JSON versionado.

Uso avulso (produção): defina DATABASE_URL e rode `python -m scripts.seed_precos`.
O JSON é apenas o insumo do seed — em runtime a fonte da verdade é o banco.
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

from app.db.conexao import get_conn

JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "dados" / "precos_planilha.json"
CATEGORIAS = ("externas", "internas", "plantas")


def semear_precos(conn: psycopg.Connection) -> dict[str, int]:
    with open(JSON_PATH, encoding="utf-8") as f:
        dados = json.load(f)

    n_cat = 0
    n_item = 0
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE preco_item, preco_categoria RESTART IDENTITY CASCADE")
        for cat in CATEGORIAS:
            bloco = dados[cat]
            cur.execute(
                "INSERT INTO preco_categoria (categoria, preco_default, descricao_padrao) "
                "VALUES (%s, %s, %s)",
                (cat, bloco["_default"], bloco["_descricao_padrao"]),
            )
            n_cat += 1
            for ordem, linha in enumerate(bloco["tabela"]):
                cur.execute(
                    "INSERT INTO preco_item (categoria, chave, descricao, preco, padroes, ordem) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (cat, linha["chave"], linha["descricao"], linha["preco"],
                     linha["padroes"], ordem),
                )
                n_item += 1
    return {"categorias": n_cat, "itens": n_item}


if __name__ == "__main__":
    conn = get_conn()
    try:
        print(semear_precos(conn))
    finally:
        conn.close()
