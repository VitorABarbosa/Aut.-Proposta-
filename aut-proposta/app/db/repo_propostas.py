"""Repositório de clientes e propostas (histórico)."""
from __future__ import annotations

import psycopg

from app.dominio.texto import normalizar


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


def _categorias_do_orcamento(orc: dict) -> list[tuple[str, dict]]:
    """Categorias reais do dict do orçamento: ignora chaves meta (iniciadas
    por "_", ex. "_categorias") e valores que não são blocos de categoria."""
    return [
        (cat, bloco) for cat, bloco in orc.items()
        if not cat.startswith("_") and isinstance(bloco, dict) and "itens" in bloco
    ]


def salvar_proposta(
    conn: psycopg.Connection,
    cliente_id: int,
    fechado: dict,
    referencia: str | None = None,
    docx_url: str | None = None,
    tabela_precos: str = "padrao",
) -> int:
    orc = fechado["orcamento"]
    fin = fechado["financeiro"]
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO propostas "
            "(cliente_id, referencia, subtotal, desconto_pct, desconto_valor, total, docx_url, tabela_precos) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (cliente_id, referencia, orc["subtotal"], fin["desconto_pct"],
             fin["desconto_valor"], fin["total"], docx_url, tabela_precos),
        )
        pid = cur.fetchone()[0]
        for cat, bloco in _categorias_do_orcamento(orc):
            for item in bloco["itens"]:
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

        out: dict = {}
        cur.execute(
            "SELECT categoria, descricao, preco FROM proposta_itens WHERE proposta_id = %s ORDER BY id",
            (pid,),
        )
        for categoria, descricao, preco in cur.fetchall():
            bloco = out.setdefault(categoria, {"qtd": 0, "total": 0, "itens": []})
            bloco["itens"].append({"desc": descricao, "preco": preco})
            bloco["qtd"] += 1
            bloco["total"] += preco
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
    """Reconstrói a estrutura (shape do parser) para copiar/reprecificar.

    As categorias na estrutura devolvida são as que o SELECT encontrar
    (dinâmicas — sem descarte de categorias fora das 3 fixas antigas).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.nome, c.contato, p.referencia, p.desconto_pct, p.tabela_precos "
            "FROM propostas p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = %s",
            (proposta_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        nome, contato, referencia, desconto_pct, tabela_precos = row

        listas: dict[str, list[str]] = {}
        cur.execute(
            "SELECT categoria, descricao FROM proposta_itens "
            "WHERE proposta_id = %s ORDER BY id",
            (proposta_id,),
        )
        for categoria, descricao in cur.fetchall():
            listas.setdefault(categoria, []).append(descricao)

    return {
        "cliente": {"empresa": nome, "ref": referencia or "", "contato": contato or ""},
        **listas,
        "desconto_pct": float(desconto_pct),
        "desconto_label": None,
        "estrategia": "planilha",
        "mostrar_precos_individuais": False,
        "tabela_precos": tabela_precos,
        "_avisos": [],
    }


def excluir_proposta(conn: psycopg.Connection, proposta_id: int) -> bool:
    """Apaga a proposta e seus itens (cascade). True se existia."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("DELETE FROM propostas WHERE id = %s", (proposta_id,))
            return cur.rowcount > 0


def listar_propostas(conn: psycopg.Connection, cliente: str | None = None) -> list[dict]:
    """Lista propostas (mais recente primeiro), com filtro opcional por cliente."""
    sql = (
        "SELECT p.id, c.nome, p.referencia, p.data, p.total, p.docx_url "
        "FROM propostas p JOIN clientes c ON c.id = p.cliente_id "
    )
    params: tuple = ()
    if cliente:
        sql += "WHERE c.nome_norm = %s "
        params = (normalizar(cliente),)
    sql += "ORDER BY p.id DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {"id": i, "cliente": nome, "referencia": ref,
             "data": data.isoformat(), "total": float(total), "docx_url": url}
            for i, nome, ref, data, total, url in cur.fetchall()
        ]
