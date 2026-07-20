"""Histórico de propostas por cliente, lido do banco.

Calcula o 'preço do último projeto do mesmo cliente' — base do 2º levantamento.
As categorias consideradas são derivadas dos dados da própria proposta
histórica (dinâmicas — não uma lista fixa).
"""
from __future__ import annotations

import psycopg

from app.db.repo_propostas import ultima_proposta_estruturada
from app.dominio.texto import normalizar


class Historico:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def _cliente_id(self, nome: str) -> int | None:
        nome_norm = normalizar(nome)
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM clientes WHERE nome_norm = %s", (nome_norm,))
            row = cur.fetchone()
        return row[0] if row else None

    def _ultima(self, nome: str) -> dict | None:
        cid = self._cliente_id(nome)
        if cid is None:
            return None
        return ultima_proposta_estruturada(self.conn, cid)

    def tem_cliente(self, nome: str) -> bool:
        return self._ultima(nome) is not None

    def medias_por_categoria(self, nome: str) -> dict[str, float] | None:
        ult = self._ultima(nome)
        if not ult:
            return None
        out: dict[str, float] = {}
        for cat, bloco in ult.items():
            if isinstance(bloco, dict) and bloco.get("qtd"):
                out[cat] = bloco["total"] / bloco["qtd"]
        return out

    def tabela_precos_inferida(self, nome: str) -> dict[str, dict[str, int]] | None:
        ult = self._ultima(nome)
        if not ult:
            return None
        tabela: dict[str, dict[str, int]] = {}
        for cat, bloco in ult.items():
            if not isinstance(bloco, dict) or "itens" not in bloco:
                continue
            tabela[cat] = {normalizar(it["desc"]): it["preco"] for it in bloco["itens"]}
        return tabela
