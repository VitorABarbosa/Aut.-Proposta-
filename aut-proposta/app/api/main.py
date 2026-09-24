"""API HTTP do serviço de propostas (consumida pelo hub flyingstudio-tools).

Auth simples de serviço interno: Bearer token fixo comparado com API_TOKEN.
Sem API_TOKEN no ambiente as rotas protegidas devolvem 503 — nunca abrem.
"""
from __future__ import annotations

import hmac
import logging
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator

from app.db.conexao import get_conn
from app.db.repo_propostas import excluir_proposta, listar_propostas
from app.db.schema import aplicar_schema
from app.docx.pdf import converter_para_pdf
from app.servicos.proposta import gerar, levantar, parse_texto
from app.storage.r2 import excluir_objetos

log = logging.getLogger("aut_proposta")


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI):
    """Aplica o schema no boot.

    O deploy não tem passo de migração: o Dockerfile sobe o uvicorn e pronto.
    Sem isto, uma coluna nova deixava o banco de produção para trás e o
    sintoma era traiçoeiro — o preview continuava funcionando (só lê) e o
    Gerar quebrava com 500 (escreve). Foi o que aconteceu com `emissor`.

    O DDL é idempotente (CREATE/ALTER ... IF NOT EXISTS), então rodar a cada
    boot não custa nada. Falha aqui não derruba a API: o container sobe, e
    /saude diz o que está faltando.
    """
    try:
        conn = _abrir_conn()
    except Exception:  # noqa: BLE001 — sem DATABASE_URL, ou banco fora
        log.exception("Schema não aplicado no boot: não consegui abrir o banco")
    else:
        try:
            aplicar_schema(conn)
            log.info("Schema aplicado no boot.")
        except Exception:  # noqa: BLE001
            log.exception("Schema não aplicado no boot")
        finally:
            _fechar_conn(conn)
    yield


app = FastAPI(title="Automação de Proposta — Flying Studio", lifespan=_ciclo_de_vida)

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
    # Só vale no caminho `texto` — com `estrutura`, o emissor vem dentro dela.
    emissor: str | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if self.texto is None and self.estrutura is None:
            raise ValueError("Envie 'texto' ou 'estrutura'.")
        return self


class CorpoProposta(BaseModel):
    texto: str | None = None
    estrutura: dict | None = None
    emissor: str | None = None

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

    # Tour virtual é proporcional à quantidade de áreas de lazer: sem esse
    # número a proposta sai com o valor de um ambiente só. Pendência (e não
    # aviso) porque a quantidade tem de ter sido perguntada, não presumida.
    from app.dominio.orcamento import e_categoria_por_ambiente
    if estrutura.get("ambientes") in (None, "") and any(
            e_categoria_por_ambiente(cat) and bloco.get("qtd")
            for cat, bloco in fechado["orcamento"].items() if isinstance(bloco, dict)):
        pend.append("Informe quantas áreas/ambientes o empreendimento tem — "
                    "o tour virtual é cobrado por ambiente.")
    return pend


def _erro_de_banco(exc: psycopg.Error) -> str:
    """Mensagem que diz o que fazer, em vez de "Internal Server Error".

    Coluna ou tabela que falta é sempre a mesma história: o código subiu e o
    banco não acompanhou.
    """
    if isinstance(exc, (psycopg.errors.UndefinedColumn, psycopg.errors.UndefinedTable)):
        return ("O banco está atrás do código (falta coluna ou tabela). "
                "Rode 'python -m scripts.migrar_catalogo_2026' com a DATABASE_URL "
                "de produção — ou reinicie o serviço, que ele aplica o schema no boot.")
    return ("O banco recusou a operação. Tente de novo; se continuar, veja os "
            "logs do serviço de propostas.")


def _falhou(acao: str, exc: Exception) -> HTTPException:
    """Registra o traceback e devolve uma mensagem que o usuário pode agir."""
    log.exception("Falha ao %s", acao)
    if isinstance(exc, psycopg.Error):
        return HTTPException(503, _erro_de_banco(exc))
    return HTTPException(500, f"Não consegui {acao}: {type(exc).__name__}. "
                              "O erro completo está nos logs do serviço.")


@app.get("/saude")
def saude():
    """Diagnóstico do serviço: o que está de pé e o que falta.

    Existe para não depender de log quando o Gerar volta 500: a resposta diz
    se o banco responde, se o schema está em dia, se dá para converter PDF e
    se o R2 está configurado.
    """
    estado: dict = {"ok": True, "banco": "sem DATABASE_URL", "schema": "não conferido",
                    "pdf": "ok" if (shutil.which("soffice") or shutil.which("libreoffice"))
                           else "LibreOffice ausente — download em PDF indisponível",
                    "r2": "ok" if os.getenv("R2_BUCKET") else "não configurado (download direto)",
                    "saidas": str(_dir_saida())}
    try:
        conn = _abrir_conn()
    except Exception as exc:  # noqa: BLE001
        estado["banco"] = f"indisponível: {type(exc).__name__}"
        estado["ok"] = False
        return estado
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("""SELECT column_name FROM information_schema.columns
                           WHERE table_name = 'propostas'""")
            colunas = {linha[0] for linha in cur.fetchall()}
            cur.execute("""SELECT table_name FROM information_schema.tables
                           WHERE table_name IN ('propostas', 'preco_item', 'chat_log')""")
            tabelas = {linha[0] for linha in cur.fetchall()}
        estado["banco"] = "ok"
        faltando = ([f"coluna propostas.{c}" for c in ("emissor", "tabela_precos")
                     if c not in colunas]
                    + [f"tabela {t}" for t in ("propostas", "preco_item", "chat_log")
                       if t not in tabelas])
        if faltando:
            estado["schema"] = "atrasado — falta: " + ", ".join(faltando)
            estado["ok"] = False
        else:
            estado["schema"] = "em dia"
    except Exception as exc:  # noqa: BLE001
        estado["banco"] = f"erro: {type(exc).__name__}"
        estado["ok"] = False
    finally:
        _fechar_conn(conn)
    return estado


@app.post("/levantamento", dependencies=[Depends(verificar_token)])
def rota_levantamento(corpo: CorpoLevantamento):
    conn = _abrir_conn()
    try:
        estrutura = (corpo.estrutura if corpo.estrutura is not None
                     else parse_texto(conn, corpo.texto, corpo.emissor))
        lev = levantar(conn, estrutura)
    except ValueError as e:  # desconto fora de faixa etc. — entrada do usuário, não erro interno
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001 — vira mensagem, não "Internal Server Error"
        raise _falhou("montar o preview", e) from None
    finally:
        _fechar_conn(conn)
    return {
        "estrutura": lev["estrutura"],
        "fechado": lev["fechado"],
        "estrategia_usada": lev["estrategia_usada"],
        "emissor": lev["emissor"],
        "avisos": lev["avisos"],
        "pendencias": _pendencias(lev["estrutura"], lev["fechado"]),
    }


@app.post("/propostas", dependencies=[Depends(verificar_token)])
def rota_gerar(corpo: CorpoProposta):
    conn = _abrir_conn()
    try:
        estrutura = (corpo.estrutura if corpo.estrutura is not None
                     else parse_texto(conn, corpo.texto, corpo.emissor))
        out = gerar(conn, estrutura, _dir_saida())
    except ValueError as e:  # desconto fora de faixa etc. — entrada do usuário, não erro interno
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001 — vira mensagem, não "Internal Server Error"
        raise _falhou("gerar a proposta", e) from None
    finally:
        _fechar_conn(conn)
    return {
        "proposta_id": out["proposta_id"],
        "docx_url": out["docx_url"],
        "download": f"/propostas/{out['proposta_id']}/docx",
        "fechado": out["fechado"],
        "emissor": out["emissor"],
        "avisos": out["avisos"],
    }


@app.get("/propostas/{proposta_id}/estrutura", dependencies=[Depends(verificar_token)])
def rota_estrutura(proposta_id: int):
    """A proposta como ela foi feita, para editar e gerar de novo."""
    from app.db.repo_propostas import obter_estrutura_de_proposta

    conn = _abrir_conn()
    try:
        estrutura = obter_estrutura_de_proposta(conn, proposta_id)
    except Exception as e:  # noqa: BLE001
        raise _falhou("abrir a proposta", e) from None
    finally:
        _fechar_conn(conn)
    if estrutura is None:
        raise HTTPException(404, "Proposta não encontrada")
    return {"estrutura": estrutura}


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
def rota_listar_propostas(cliente: str | None = None):
    conn = _abrir_conn()
    try:
        propostas = listar_propostas(conn, cliente)
    finally:
        _fechar_conn(conn)
    for p in propostas:
        p["download"] = f"/propostas/{p['id']}/docx"
        p["pdf"] = f"/propostas/{p['id']}/pdf"
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


def _chaves_r2_da_proposta(docx_url: str | None, proposta_id: int) -> list[str]:
    if docx_url and "/Propostas/" in docx_url:
        chave = "Propostas/" + docx_url.split("/Propostas/", 1)[1]
    else:
        chave = f"propostas/proposta_{proposta_id}.docx"  # padrão legado
    return [chave]


@app.delete("/propostas/{proposta_id}", dependencies=[Depends(verificar_token)])
def rota_deletar_proposta(proposta_id: int):
    conn = _abrir_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT docx_url FROM propostas WHERE id = %s", (proposta_id,))
            row = cur.fetchone()
        docx_url = row[0] if row else None
        if row is None or not excluir_proposta(conn, proposta_id):
            raise HTTPException(404, "Proposta não encontrada")
        # Os SELECTs acima abrem transação implícita na conexão, o que rebaixa
        # o conn.transaction() de excluir_proposta a SAVEPOINT — sem este
        # commit, o close() da conexão descartaria a exclusão (mesmo bug de
        # app/servicos/proposta.py:gerar).
        conn.commit()
    finally:
        _fechar_conn(conn)

    excluir_objetos(_chaves_r2_da_proposta(docx_url, proposta_id))
    for ext in (".docx", ".pdf"):
        arq = _dir_saida() / f"proposta_{proposta_id}{ext}"
        if arq.exists():
            arq.unlink()
    return {"excluida": proposta_id}
