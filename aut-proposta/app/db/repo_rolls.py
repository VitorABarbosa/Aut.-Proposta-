"""Repositório dos rolls: cada versão é uma linha, e a última manda.

O roll de um projeto não é um documento só: é uma sequência. Guardar todas as
versões é o que permite dizer o que entrou e o que saiu quando o cliente
atualiza — que é a pergunta que se faz toda vez que um roll novo chega.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from app.dominio.texto import normalizar
from app.empresas import EMISSOR_PADRAO


def _ref_norm(referencia: str | None) -> str:
    return normalizar(referencia or "")


def ultimo_roll(conn: psycopg.Connection, cliente_id: int, referencia: str | None,
                emissor: str = EMISSOR_PADRAO) -> dict[str, Any] | None:
    """A versão mais recente do roll daquele projeto, ou None se é o primeiro.

    O empreendimento casa normalizado — "Vila Mariana" e "VILA MARIANA" são o
    mesmo projeto, e um acento a mais não pode abrir uma segunda sequência de
    versões do mesmo roll. A normalização é a do Python (a mesma do resto do
    sistema), por isso o filtro de referência acontece aqui e não no SQL.
    """
    alvo = _ref_norm(referencia)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, versao, nome_arquivo, estrutura, referencia, data FROM rolls "
            "WHERE cliente_id = %s AND emissor = %s ORDER BY versao DESC, id DESC",
            (cliente_id, emissor),
        )
        for rid, versao, nome, estrutura, ref, data in cur.fetchall():
            if _ref_norm(ref) != alvo:
                continue
            return {"id": rid, "versao": versao, "nome_arquivo": nome,
                    "estrutura": estrutura, "data": data.isoformat()}
    return None


def salvar_roll(conn: psycopg.Connection, cliente_id: int, estrutura: dict[str, Any],
                referencia: str | None, emissor: str, versao: int,
                nome_arquivo: str, docx_url: str | None = None) -> int:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO rolls (cliente_id, referencia, emissor, versao, nome_arquivo, "
            "estrutura, docx_url) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (cliente_id, referencia, emissor, versao, nome_arquivo,
             json.dumps(estrutura, ensure_ascii=False, default=str), docx_url),
        )
        return cur.fetchone()[0]


def atualizar_docx_url(conn: psycopg.Connection, roll_id: int, docx_url: str) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("UPDATE rolls SET docx_url = %s WHERE id = %s", (docx_url, roll_id))


def obter_roll(conn: psycopg.Connection, roll_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.id, c.nome, r.referencia, r.emissor, r.versao, r.nome_arquivo, "
            "r.estrutura, r.docx_url, r.data FROM rolls r "
            "JOIN clientes c ON c.id = r.cliente_id WHERE r.id = %s",
            (roll_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    rid, cliente, ref, emissor, versao, nome, estrutura, url, data = row
    return {"id": rid, "cliente": cliente, "referencia": ref, "emissor": emissor,
            "versao": versao, "nome_arquivo": nome, "estrutura": estrutura,
            "docx_url": url, "data": data.isoformat()}


def listar_rolls(conn: psycopg.Connection, cliente: str | None = None) -> list[dict[str, Any]]:
    """Rolls do mais recente para o mais antigo, com a contagem de imagens de
    cada versão — que é o número que a pessoa procura ao abrir a lista."""
    from app.dominio.roll import total_de_imagens

    sql = ("SELECT r.id, c.nome, r.referencia, r.emissor, r.versao, r.nome_arquivo, "
           "r.estrutura, r.docx_url, r.data FROM rolls r "
           "JOIN clientes c ON c.id = r.cliente_id ")
    params: tuple = ()
    if cliente:
        sql += "WHERE c.nome_norm = %s "
        params = (normalizar(cliente),)
    sql += "ORDER BY r.id DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        linhas = cur.fetchall()
    return [
        {"id": rid, "cliente": nome, "referencia": ref, "emissor": emissor,
         "versao": versao, "nome_arquivo": arquivo, "docx_url": url,
         "data": data.isoformat(),
         "imagens": total_de_imagens((estrutura or {}).get("blocos") or [])}
        for rid, nome, ref, emissor, versao, arquivo, estrutura, url, data in linhas
    ]


def excluir_roll(conn: psycopg.Connection, roll_id: int) -> bool:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM rolls WHERE id = %s", (roll_id,))
        return cur.rowcount > 0
