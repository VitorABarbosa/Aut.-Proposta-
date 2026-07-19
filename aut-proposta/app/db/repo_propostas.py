"""Repositório de clientes e propostas (histórico)."""
from __future__ import annotations

import psycopg

from app.dominio.texto import normalizar

CATEGORIAS = ("externas", "internas", "plantas")


def upsert_cliente(conn: psycopg.Connection, nome: str, contato: str | None = None) -> int:
    nome_norm = normalizar(nome)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM clientes WHERE nome_norm = %s", (nome_norm,))
        row = cur.fetchone()
        if row:
            return row[0]
        with conn.transaction():
            cur.execute(
                "INSERT INTO clientes (nome, nome_norm, contato) VALUES (%s, %s, %s) RETURNING id",
                (nome, nome_norm, contato),
            )
            novo_id = cur.fetchone()[0]
    return novo_id


def salvar_proposta(
    conn: psycopg.Connection,
    cliente_id: int,
    fechado: dict,
    referencia: str | None = None,
    docx_url: str | None = None,
) -> int:
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO propostas "
            "(cliente_id, referencia, subtotal, desconto_pct, desconto_valor, total, docx_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (cliente_id, referencia, orc["subtotal"], fin["desconto_pct"],
             fin["desconto_valor"], fin["total"], docx_url),
        )
        pid = cur.fetchone()[0]
        for cat in CATEGORIAS:
            for item in orc[cat]["itens"]:
                cur.execute(
                    "INSERT INTO proposta_itens (proposta_id, categoria, descricao, preco, origem) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (pid, cat, item["descricao"], item["preco"], item.get("fonte", "")),
                )
    return pid


def ultima_proposta_estruturada(conn: psycopg.Connection, cliente_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM propostas WHERE cliente_id = %s ORDER BY data DESC, id DESC LIMIT 1",
            (cliente_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        pid = row[0]

        out: dict = {cat: {"qtd": 0, "total": 0, "itens": []} for cat in CATEGORIAS}
        cur.execute(
            "SELECT categoria, descricao, preco FROM proposta_itens WHERE proposta_id = %s ORDER BY id",
            (pid,),
        )
        for categoria, descricao, preco in cur.fetchall():
            if categoria in out:
                out[categoria]["itens"].append({"desc": descricao, "preco": preco})
                out[categoria]["qtd"] += 1
                out[categoria]["total"] += preco
    return out


def atualizar_docx_url(conn: psycopg.Connection, proposta_id: int, docx_url: str) -> None:
    """Grava a URL do .docx (R2) numa proposta já salva."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE propostas SET docx_url = %s WHERE id = %s",
                (docx_url, proposta_id),
            )


def obter_estrutura_de_proposta(conn: psycopg.Connection, proposta_id: int) -> dict | None:
    """Reconstrói a estrutura (shape do parser) para copiar/reprecificar."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.nome, c.contato, p.referencia, p.desconto_pct "
            "FROM propostas p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = %s",
            (proposta_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        nome, contato, referencia, desconto_pct = row

        listas: dict[str, list[str]] = {cat: [] for cat in CATEGORIAS}
        cur.execute(
            "SELECT categoria, descricao FROM proposta_itens "
            "WHERE proposta_id = %s ORDER BY id",
            (proposta_id,),
        )
        for categoria, descricao in cur.fetchall():
            if categoria in listas:
                listas[categoria].append(descricao)

    return {
        "cliente": {"empresa": nome, "ref": referencia or "", "contato": contato or ""},
        **listas,
        "desconto_pct": float(desconto_pct),
        "desconto_label": None,
        "estrategia": "planilha",
        "mostrar_precos_individuais": False,
        "_avisos": [],
    }


def excluir_proposta(conn: psycopg.Connection, proposta_id: int) -> bool:
    """Apaga a proposta e seus itens (cascade). True se existia."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("DELETE FROM propostas WHERE id = %s", (proposta_id,))
            return cur.rowcount > 0
