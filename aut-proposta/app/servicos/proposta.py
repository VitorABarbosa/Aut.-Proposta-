"""Orquestração de uma proposta: NEON -> orçamento -> .docx -> R2 -> NEON.

Único lugar que decide a estratégia (planilha × histórico) e o único caminho
de produção que monta TabelaPrecos — sempre via carregar_tabela_precos(conn).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from app.db.repo_precos import carregar_tabela_precos
from app.db.repo_propostas import atualizar_docx_url, salvar_proposta, upsert_cliente
from app.docx.gerador import gerar_docx
from app.dominio.descontos import Desconto
from app.dominio.orcamento import fechar_orcamento, orcar_pela_planilha
from app.historico.historico import Historico
from app.historico.orcamento_historico import orcar_pelo_historico
from app.storage.r2 import enviar_docx


def _descricoes(estrutura: dict[str, Any]) -> dict[str, list[str]]:
    return {cat: estrutura.get(cat, []) for cat in ("externas", "internas", "plantas")}


def levantar(conn: psycopg.Connection, estrutura: dict[str, Any]) -> dict[str, Any]:
    """Resolve estratégia e preços (NEON) e devolve o orçamento fechado."""
    avisos = list(estrutura.get("_avisos", []))
    tabela = carregar_tabela_precos(conn)
    descricoes = _descricoes(estrutura)
    empresa = estrutura["cliente"]["empresa"]
    pedida = estrutura.get("estrategia", "auto")

    historico = Historico(conn)
    orc = None
    if pedida == "historico" or (pedida == "auto" and historico.tem_cliente(empresa)):
        orc = orcar_pelo_historico(historico, empresa, descricoes, tabela)
        if orc is None and pedida == "historico":
            avisos.append(f"Cliente '{empresa}' não tem histórico — usei a tabela de planilha.")
    if orc is None:
        orc = orcar_pela_planilha(descricoes, tabela)

    desconto = None
    if estrutura.get("desconto_pct", 0):
        desconto = Desconto(
            tipo="percentual",
            valor=float(estrutura["desconto_pct"]),
            rotulo=estrutura.get("desconto_label") or "",
        )

    return {
        "cliente": estrutura["cliente"],
        "fechado": fechar_orcamento(orc, desconto),
        "estrategia_usada": orc.estrategia,
        "avisos": avisos,
    }


def gerar(conn: psycopg.Connection, estrutura: dict[str, Any], dir_saida: Path) -> dict[str, Any]:
    """Levanta, persiste no NEON, gera o .docx e tenta subir no R2."""
    lev = levantar(conn, estrutura)
    cliente = lev["cliente"]
    fechado = lev["fechado"]

    cliente_id = upsert_cliente(conn, cliente["empresa"], cliente.get("contato"))
    proposta_id = salvar_proposta(conn, cliente_id, fechado, referencia=cliente.get("ref"))

    docx_path = Path(dir_saida) / f"proposta_{proposta_id}.docx"
    gerar_docx(
        cliente,
        fechado,
        docx_path,
        mostra_precos_individuais=bool(estrutura.get("mostrar_precos_individuais")),
    )

    chave = f"propostas/proposta_{proposta_id}.docx"
    docx_url = enviar_docx(docx_path, chave)
    if docx_url:
        atualizar_docx_url(conn, proposta_id, docx_url)
    else:
        lev["avisos"].append("Upload no R2 indisponível — use o download direto da API.")

    # Os SELECTs de levantar abrem transação implícita na conexão, o que rebaixa
    # os conn.transaction() dos repositórios a SAVEPOINTs — sem este commit, o
    # close() da conexão descartaria a proposta inteira.
    conn.commit()

    return {
        "proposta_id": proposta_id,
        "docx_path": str(docx_path),
        "docx_url": docx_url,
        "fechado": fechado,
        "avisos": lev["avisos"],
    }
