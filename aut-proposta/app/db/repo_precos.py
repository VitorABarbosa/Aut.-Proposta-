"""Carrega a tabela de preços do banco, montando a estrutura que TabelaPrecos espera."""
from __future__ import annotations

import psycopg

from app.dominio.precos import CATEGORIAS_VALIDAS, TabelaPrecos


def carregar_tabela_precos(conn: psycopg.Connection) -> TabelaPrecos:
    dados: dict = {}
    with conn.cursor() as cur:
        cur.execute("SELECT categoria, preco_default, descricao_padrao FROM preco_categoria")
        for categoria, preco_default, descricao_padrao in cur.fetchall():
            dados[categoria] = {
                "_default": preco_default,
                "_descricao_padrao": descricao_padrao,
                "tabela": [],
            }

        cur.execute(
            "SELECT categoria, chave, descricao, preco, padroes "
            "FROM preco_item ORDER BY categoria, ordem"
        )
        for categoria, chave, descricao, preco, padroes in cur.fetchall():
            dados[categoria]["tabela"].append(
                {"chave": chave, "descricao": descricao, "preco": preco, "padroes": padroes}
            )

    # Garante que as categorias base existam (mesmo que sem linhas).
    for cat in CATEGORIAS_VALIDAS:
        dados.setdefault(cat, {"_default": 0, "_descricao_padrao": "", "tabela": []})

    return TabelaPrecos(dados)
