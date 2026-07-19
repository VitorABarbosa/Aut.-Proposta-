"""API HTTP do serviço de propostas (consumida pelo hub flyingstudio-tools).

Auth simples de serviço interno: Bearer token fixo comparado com API_TOKEN.
Sem API_TOKEN no ambiente as rotas protegidas devolvem 503 — nunca abrem.
"""
from __future__ import annotations

import hmac
import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator

from app.db.conexao import get_conn
from app.db.repo_propostas import excluir_proposta, listar_propostas
from app.docx.pdf import converter_para_pdf
from app.ia.parser import parse
from app.servicos.proposta import gerar, levantar
from app.storage.r2 import excluir_objetos

app = FastAPI(title="Automação de Proposta — Flying Studio")

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _dir_saida() -> Path:
    return Path(os.getenv("PROPOSTAS_DIR", "saidas"))


# Indireção para os testes injetarem a conexão do fixture db.
def _abrir_conn():
    return get_conn()


def _fechar_conn(conn) -> None:
    conn.close()


def verificar_token(request: Request) -> None:
    esperado = os.getenv("API_TOKEN")
    if not esperado:
        raise HTTPException(503, "API_TOKEN não configurado")
    recebido = request.headers.get("Authorization", "")
    if not hmac.compare_digest(recebido.encode(), f"Bearer {esperado}".encode()):
        raise HTTPException(401, "Token inválido")


class CorpoLevantamento(BaseModel):
    texto: str | None = None
    estrutura: dict | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if self.texto is None and self.estrutura is None:
            raise ValueError("Envie 'texto' ou 'estrutura'.")
        return self


class CorpoProposta(BaseModel):
    texto: str | None = None
    estrutura: dict | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if self.texto is None and self.estrutura is None:
            raise ValueError("Envie 'texto' ou 'estrutura'.")
        return self


def _pendencias(estrutura: dict, fechado: dict) -> list[str]:
    """Requisitos obrigatórios de toda proposta; defaults do parser contam como faltando."""
    pend: list[str] = []
    cli = estrutura.get("cliente", {})

    # Cliente assumido pelo parser (não marcado explicitamente) só conta como
    # pendência enquanto a empresa CONTINUAR sendo o valor assumido — a UI
    # reenvia a estrutura com os _avisos antigos, e editar o campo deve limpar.
    assumido = None
    for a in estrutura.get("_avisos", []):
        m = re.search(r"assumi '([^']+)'", a)
        if m:
            assumido = m.group(1)
            break

    if not cli.get("empresa") or cli["empresa"] in ("CLIENTE", assumido):
        pend.append("Informe a construtora/incorporadora (cliente).")
    if not cli.get("ref") or cli["ref"] == "PROJETO":
        pend.append("Informe o empreendimento/projeto (ref).")
    if not cli.get("contato") or cli["contato"] == "—":
        pend.append("Informe o A/C — responsável que recebe a proposta.")
    if fechado["orcamento"]["total_imagens"] == 0:
        pend.append("Nenhum item identificado — liste as imagens/serviços contratados.")
    return pend


@app.get("/saude")
def saude():
    return {"ok": True}


@app.post("/levantamento", dependencies=[Depends(verificar_token)])
def rota_levantamento(corpo: CorpoLevantamento):
    estrutura = corpo.estrutura if corpo.estrutura is not None else parse(corpo.texto)
    conn = _abrir_conn()
    try:
        lev = levantar(conn, estrutura)
    except ValueError as e:  # desconto fora de faixa etc. — entrada do usuário, não erro interno
        raise HTTPException(422, str(e))
    finally:
        _fechar_conn(conn)
    return {
        "estrutura": estrutura,
        "fechado": lev["fechado"],
        "estrategia_usada": lev["estrategia_usada"],
        "avisos": lev["avisos"],
        "pendencias": _pendencias(estrutura, lev["fechado"]),
    }


@app.post("/propostas", dependencies=[Depends(verificar_token)])
def rota_gerar(corpo: CorpoProposta):
    estrutura = corpo.estrutura if corpo.estrutura is not None else parse(corpo.texto)
    conn = _abrir_conn()
    try:
        out = gerar(conn, estrutura, _dir_saida())
    except ValueError as e:  # desconto fora de faixa etc. — entrada do usuário, não erro interno
        raise HTTPException(422, str(e))
    finally:
        _fechar_conn(conn)
    return {
        "proposta_id": out["proposta_id"],
        "docx_url": out["docx_url"],
        "download": f"/propostas/{out['proposta_id']}/docx",
        "fechado": out["fechado"],
        "avisos": out["avisos"],
    }


@app.get("/propostas/{proposta_id}/docx", dependencies=[Depends(verificar_token)])
def rota_download(proposta_id: int):
    caminho = _dir_saida() / f"proposta_{proposta_id}.docx"
    if not caminho.exists():
        raise HTTPException(404, "Proposta não encontrada")
    return FileResponse(caminho, media_type=MIME_DOCX,
                        filename=f"proposta_{proposta_id}.docx")


@app.get("/propostas/{proposta_id}/pdf", dependencies=[Depends(verificar_token)])
def rota_download_pdf(proposta_id: int):
    docx = _dir_saida() / f"proposta_{proposta_id}.docx"
    pdf = docx.with_suffix(".pdf")
    if not pdf.exists():
        if not docx.exists():
            raise HTTPException(404, "Proposta não encontrada")
        pdf_gerado = converter_para_pdf(docx)
        if pdf_gerado is None:
            raise HTTPException(501, "Conversor PDF (LibreOffice) indisponível neste servidor")
        pdf = pdf_gerado
    return FileResponse(pdf, media_type="application/pdf",
                        filename=f"proposta_{proposta_id}.pdf")


@app.get("/propostas", dependencies=[Depends(verificar_token)])
def rota_listar_propostas(cliente: str):
    conn = _abrir_conn()
    try:
        propostas = listar_propostas(conn, cliente)
    finally:
        _fechar_conn(conn)
    return {"propostas": propostas}


class CorpoChat(BaseModel):
    mensagens: list[dict] = []


@app.post("/chat", dependencies=[Depends(verificar_token)])
def rota_chat(corpo: CorpoChat):
    from app.ia.chat import responder
    conn = _abrir_conn()
    try:
        return responder(conn, corpo.mensagens)
    finally:
        _fechar_conn(conn)


@app.delete("/propostas/{proposta_id}", dependencies=[Depends(verificar_token)])
def rota_deletar_proposta(proposta_id: int):
    conn = _abrir_conn()
    try:
        # Primeiro obtém a proposta para recuperar a chave R2
        from app.db.repo_propostas import obter_estrutura_de_proposta
        estrutura = obter_estrutura_de_proposta(conn, proposta_id)
        if not estrutura:
            raise HTTPException(404, "Proposta não encontrada")

        # Tenta recuperar a chave R2 para exclusão (se disponível em docx_url)
        with conn.cursor() as cur:
            cur.execute("SELECT docx_url FROM propostas WHERE id = %s", (proposta_id,))
            row = cur.fetchone()
            docx_url = row[0] if row else None

        # Apaga a proposta do banco
        resultado = excluir_proposta(conn, proposta_id)
        if not resultado:
            raise HTTPException(404, "Proposta não encontrada")

        # Tenta apagar do R2 (será None se não estava subida)
        if docx_url:
            # Extrai a chave da URL (está no final após o último /)
            chave = docx_url.split("/")[-3:] if "/" in docx_url else []
            if chave and len(chave) >= 3:
                # Reconstrói a chave completa
                chave_r2 = f"Propostas/{chave[-3]}/{chave[-2]}/{chave[-1]}"
                excluir_objetos([chave_r2])

        # Apaga o arquivo local se existir
        docx_path = _dir_saida() / f"proposta_{proposta_id}.docx"
        if docx_path.exists():
            docx_path.unlink()
        pdf_path = docx_path.with_suffix(".pdf")
        if pdf_path.exists():
            pdf_path.unlink()

    finally:
        _fechar_conn(conn)
    return {"excluida": proposta_id}
