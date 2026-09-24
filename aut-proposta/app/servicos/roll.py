"""Ler um roll, comparar com a versão anterior e gerar a próxima.

O fluxo é o que a pessoa faz hoje à mão: abre o roll que chegou, compara com o
último que saiu, vê o que o cliente cortou e o que pediu a mais, e salva o
arquivo novo com o nome da vez — Roll_Flying, depois _Atl, depois _Atl_1.
"""
from __future__ import annotations

import base64
import datetime as dt
from pathlib import Path
from typing import Any

import psycopg

from app.db.repo_propostas import upsert_cliente
from app.db.repo_rolls import atualizar_docx_url, salvar_roll, ultimo_roll
from app.docx.roll import gerar_roll_docx
from app.dominio.roll import diferenca, total_de_imagens
from app.empresas import EMISSOR_PADRAO, empresa as empresa_emissora
from app.ia.leitura_roll import ler
from app.ia.pdf import texto_do_pdf
from app.ia.visao import MAX_IMAGENS, normalizar_imagem
from app.servicos.nomes import limpar, nome_do_roll
from app.servicos.proposta import _slug
from app.storage.r2 import enviar_docx


def _texto_dos_pdfs(pdfs: list[str]) -> str:
    """PDFs em base64 (ou data URL) viram um texto só, na ordem em que vieram."""
    partes = []
    for cru in pdfs:
        dados = cru.split(",", 1)[-1] if cru.startswith("data:") else cru
        try:
            texto = texto_do_pdf(base64.b64decode(dados))
        except Exception as e:  # noqa: BLE001 — arquivo ruim é erro de entrada
            raise ValueError(
                "Não consegui abrir esse PDF. Exporta o roll de novo pelo Word, "
                "ou manda um print dele."
            ) from e
        if texto.strip():
            partes.append(texto)
    return "\n\n".join(partes)


def interpretar(texto: str = "", pdfs: list[str] | None = None,
                imagens: list[str] | None = None) -> dict[str, Any]:
    """O roll que chegou, em seções e itens. Aceita PDF, print ou texto colado.

    PDF escaneado não tem camada de texto e sai vazio na extração; aí ele
    ainda pode vir como print, que é o caminho da visão.
    """
    do_pdf = _texto_dos_pdfs(pdfs or [])
    juntos = "\n\n".join(p for p in (do_pdf, texto.strip()) if p)
    preparadas = [normalizar_imagem(u) for u in (imagens or [])[:MAX_IMAGENS]]
    if not juntos and not preparadas:
        raise ValueError("Mande o roll: o PDF, um print dele ou a lista colada.")
    return ler(juntos, preparadas)


def gerar(conn: psycopg.Connection, roll: dict[str, Any], dir_saida: Path,
          emissor: str | None = None, data: dt.date | None = None) -> dict[str, Any]:
    """Grava a versão nova do roll, escreve o .docx e diz o que mudou."""
    emp = empresa_emissora(emissor or roll.get("emissor") or EMISSOR_PADRAO)
    cliente = roll.get("cliente") or {}
    if not (cliente.get("empresa") or "").strip():
        raise ValueError("O roll precisa do cliente: de quem é o empreendimento?")
    blocos = roll.get("blocos") or []
    if not blocos:
        raise ValueError("O roll está vazio: nenhuma seção com item foi reconhecida.")

    cliente_id = upsert_cliente(conn, cliente["empresa"])
    anterior = ultimo_roll(conn, cliente_id, cliente.get("ref"), emp.chave)
    versao = (anterior["versao"] + 1) if anterior else 0
    mudou = diferenca((anterior["estrutura"] or {}).get("blocos") or [], blocos) if anterior else None

    # O nome pode ser escrito à mão, como o da proposta; sem isso, o da vez.
    nome = limpar(roll.get("nome_arquivo") or "") or nome_do_roll(emp.chave, versao)
    guardado = {**roll, "emissor": emp.chave, "nome_arquivo": nome, "versao": versao}

    roll_id = salvar_roll(conn, cliente_id, guardado, cliente.get("ref"),
                          emp.chave, versao, nome)

    caminho = Path(dir_saida) / f"roll_{roll_id}.docx"
    gerar_roll_docx(cliente, guardado, caminho, data=data, emissor=emp.chave)

    chave = (f"Rolls/{emp.chave}/{_slug(cliente['empresa'])}"
             f"/{_slug(cliente.get('ref') or 'geral')}/{roll_id}_{nome}.docx")
    docx_url = enviar_docx(caminho, chave)
    if docx_url:
        atualizar_docx_url(conn, roll_id, docx_url)
    conn.commit()

    return {
        "roll_id": roll_id,
        "versao": versao,
        "nome_arquivo": nome,
        "emissor": emp.chave,
        "imagens": total_de_imagens(blocos),
        "docx_url": docx_url,
        "chave_r2": chave,
        "anterior": {"id": anterior["id"], "nome_arquivo": anterior["nome_arquivo"]} if anterior else None,
        "mudou": mudou,
        "avisos": roll.get("avisos") or [],
    }
