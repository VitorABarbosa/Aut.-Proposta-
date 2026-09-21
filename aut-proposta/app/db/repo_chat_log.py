"""Registro das rodadas do chat, para medir a inteligência.

Grava mensagens, chamadas de ferramenta (nome, argumentos, resultado), a
resposta final, o modelo e a duração. Casos que deram errado viram casos-ouro
em `tests/ia/casos/` e rodam em `scripts/avaliar_chat.py`.

A gravação nunca pode derrubar o chat: qualquer falha aqui é engolida e a
resposta segue para o usuário.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg


def registrar_rodada(conn: psycopg.Connection, *, modelo: str | None, mensagens: list,
                     ferramentas: list[dict], resposta: dict, emissor: str | None,
                     duracao_ms: int, erro: str | None = None) -> int | None:
    """Devolve o id gravado, ou None se a gravação falhou (nunca levanta)."""
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_log (modelo, mensagens, ferramentas, resposta, emissor, "
                "duracao_ms, erro) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (modelo, _json(mensagens), _json(ferramentas), _json(resposta),
                 emissor, duracao_ms, erro),
            )
            novo_id = cur.fetchone()[0]
        # A rota do chat fecha a conexão sem commit, e os SELECTs de levantar
        # já abriram transação implícita — sem isto o INSERT seria descartado.
        conn.commit()
        return novo_id
    except Exception:  # noqa: BLE001 — registro é acessório
        return None


def listar_rodadas(conn: psycopg.Connection, limite: int = 50) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, criado_em, modelo, mensagens, ferramentas, resposta, emissor, "
            "duracao_ms, erro FROM chat_log ORDER BY id DESC LIMIT %s", (limite,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, linha)) for linha in cur.fetchall()]


def _json(valor: Any) -> str:
    """Prints em base64 não vão para o log: um data URL de 1 MB por rodada
    inviabiliza a tabela, e a transcrição em texto já está nas mensagens."""
    return json.dumps(_sem_base64(valor), ensure_ascii=False, default=str)


def _sem_base64(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _sem_base64(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sem_base64(v) for v in valor]
    if isinstance(valor, str) and valor.startswith("data:image/"):
        return f"<imagem {len(valor)} bytes>"
    return valor
