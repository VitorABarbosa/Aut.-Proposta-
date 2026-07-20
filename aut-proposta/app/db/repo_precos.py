"""Carrega a tabela de preços do banco, montando a estrutura que TabelaPrecos espera."""
from __future__ import annotations

import psycopg

from app.dominio.precos import TabelaPrecos


def carregar_tabela_precos(conn: psycopg.Connection, tabela: str = "padrao") -> TabelaPrecos:
    """Carrega a tabela de preços `tabela` ("padrao" ou "mcmv") do NEON.

    Devolve o que existir no banco, na ordem de `ordem` — sem completar com
    as 3 categorias fixas: uma tabela nova pode ter só as categorias que o
    catálogo definir. Cada categoria ganha, além dos metadados já existentes
    (`_default`, `_descricao_padrao`), os metadados de catálogo: `_ordem`,
    `_rotulo` (rótulo usado no docx) e `_prefixo`.
    """
    dados: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT categoria, preco_default, descricao_padrao, ordem, rotulo_docx, prefixo "
            "FROM preco_categoria WHERE tabela = %s ORDER BY ordem",
            (tabela,),
        )
        for categoria, preco_default, descricao_padrao, ordem, rotulo_docx, prefixo in cur.fetchall():
            dados[categoria] = {
                "_default": preco_default,
                "_descricao_padrao": descricao_padrao,
                "_ordem": ordem,
                "_rotulo": rotulo_docx,
                "_prefixo": prefixo,
                "tabela": [],
            }

        cur.execute(
            "SELECT categoria, chave, descricao, preco, padroes "
            "FROM preco_item WHERE tabela = %s ORDER BY categoria, ordem",
            (tabela,),
        )
        for categoria, chave, descricao, preco, padroes in cur.fetchall():
            dados[categoria]["tabela"].append(
                {"chave": chave, "descricao": descricao, "preco": preco, "padroes": padroes}
            )

    return TabelaPrecos(dados)
