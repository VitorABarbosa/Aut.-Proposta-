# Automação de Proposta — Plano 5: Chat livre, Consultas, Histórico e Exclusão Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat descontraído que conduz a proposta ("Oi, tudo bem? O que vamos fazer hoje?"), aceita tudo de uma vez ou pergunta o que falta, consulta/copia propostas anteriores; R2 organizado por `Propostas/{cliente}/{projeto}/`; histórico visível no Workspace com re-download de docx/pdf e exclusão definitiva (NEON + R2) com confirmação.

**Architecture:** Backend continua dono de TODA a lógica. Novo `POST /chat` **stateless** (o front envia o histórico de mensagens): a IA (OpenAI tools/function-calling) conversa e usa 3 ferramentas internas — `precificar_proposta` (chama `levantar`, único caminho de preço), `listar_propostas_cliente` e `carregar_proposta` (para copiar mudando valores) — e **nunca produz número**. Novos repositórios de consulta/exclusão; chaves R2 com slugs de cliente/projeto. No hub, o agente ganha abas: **Chat** (bolhas + quick replies + preview ao vivo), **Texto direto** (painel atual, fallback offline) e **Histórico** (lista, download, excluir).

**Tech Stack:** o já existente (FastAPI, psycopg3, OpenAI `gpt-4o-mini`, boto3, python-docx; Next.js 14 + TS + Tailwind + Jest).

## Roadmap (contexto)

Planos 1-4 ✅ (núcleo, NEON+histórico, docx+IA+API, UI+deploy). **Plano 5 (este):** chat conversacional + consultas + organização/gestão do acervo.

## Dois repositórios

- **aut-proposta** (Tasks 1-4): branch `feat/plano-5-chat-consultas`.
- **hub** `flyingstudio-tools` (Tasks 5-6): branch `feat/proposta-chat-historico`, em worktree isolado como no Plano 4 (`git worktree add .worktrees/proposta-chat -b feat/proposta-chat-historico origin/master` + `npm ci`).

## Global Constraints

- **Toda lógica no serviço**; hub só exibe e repassa via proxy existente (`/api/tools/proposta/[...route]` é catch-all — cobre as rotas novas sem mudança).
- **A IA nunca produz um número**: preços só via ferramenta `precificar_proposta` → `levantar(conn, estrutura)`. O texto da IA pode CITAR valores que a ferramenta devolveu, nunca inventá-los.
- `POST /chat` é stateless: request `{"mensagens": [{"role": "user"|"assistant", "content": str}, ...]}`; response `{"mensagem": str, "quick_replies": [str], "levantamento": {...}|null}` — `levantamento` (mesmo shape do `/levantamento`, com `pendencias`) presente quando a IA precificou nesta rodada.
- Sem `OPENAI_API_KEY` ou falha da API: `/chat` responde `{"mensagem": "O chat precisa da IA... use a aba 'Texto direto'.", "quick_replies": [], "levantamento": null}` — nunca 500.
- Persona do chat: descontraída e direta, em português; abertura padrão "Oi, tudo bem? O que vamos fazer hoje?"; quick replies iniciais: `["Nova proposta", "Consultar cliente", "Copiar proposta anterior"]`.
- Chaves R2 novas: `Propostas/{slug_cliente}/{slug_projeto}/proposta_{id}.docx` com `slug = normalizar(texto)` (de `app.dominio.texto`) trocando espaços por `-`. Objetos antigos não são migrados.
- Exclusão: `DELETE /propostas/{id}` apaga NEON (itens+proposta via cascade), objetos R2 da proposta e arquivos locais em `PROPOSTAS_DIR`; devolve `{"excluida": id}`; 404 se não existe. Na UI, botão com **confirmação explícita** antes de chamar.
- Testes sem rede (OpenAI/boto3 monkeypatched); testes de banco com `@pytest.mark.db` + fixture `db`; hub com Jest. Rodar pytest de `aut-proposta/`, npm da raiz do worktree.
- Código do serviço em português; hub em TS com texto de UI em português. O código real de cada repo governa sobre snippets deste plano.

---

### Task 1: Backend — chaves R2 organizadas + exclusão de objetos

**Files:**
- Modify: `aut-proposta/app/storage/r2.py` (add `excluir_objetos`)
- Modify: `aut-proposta/app/servicos/proposta.py` (chave nova com slugs; expõe `chave_r2`)
- Test: `aut-proposta/tests/storage/test_r2.py`, `aut-proposta/tests/servicos/test_proposta.py` (adições)

**Interfaces:**
- Produces:
  - `app.storage.r2.excluir_objetos(chaves: list[str]) -> int` — deleta cada chave; devolve quantos pedidos foram enviados; sem credenciais ou erro → 0/ignora (nunca levanta).
  - `app.servicos.proposta._slug(texto: str) -> str` — `normalizar(texto)` com espaços→`-`.
  - `gerar(...)` passa a usar `chave = f"Propostas/{_slug(empresa)}/{_slug(ref)}/proposta_{id}.docx"` e inclui `"chave_r2": chave` no dict de retorno.

- [ ] **Step 1: Testes (falha primeiro)** — em `tests/storage/test_r2.py` adicionar:

```python
def test_excluir_objetos_chama_delete(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)
    apagadas = []

    class FakeS3:
        def delete_object(self, Bucket, Key):
            apagadas.append((Bucket, Key))

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())
    n = r2.excluir_objetos(["Propostas/galli/aurora/proposta_1.docx"])
    assert n == 1
    assert apagadas == [("propostas", "Propostas/galli/aurora/proposta_1.docx")]


def test_excluir_sem_credenciais_devolve_zero(monkeypatch):
    _limpa_envs(monkeypatch)
    assert r2.excluir_objetos(["x"]) == 0
```

Em `tests/servicos/test_proposta.py` adicionar:

```python
def test_gerar_usa_chave_organizada_por_cliente_projeto(db, tmp_path, monkeypatch):
    _prep(db)
    chaves = []
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: chaves.append(chave) or f"https://r2/{chave}")
    out = svc.gerar(db, _estrutura(), tmp_path)
    esperado = f"Propostas/galli/residencial-aurora/proposta_{out['proposta_id']}.docx"
    assert chaves == [esperado]
    assert out["chave_r2"] == esperado
```

Run: `pytest tests/storage tests/servicos -v` → FAIL.

- [ ] **Step 2: Implementar** — em `r2.py`:

```python
def excluir_objetos(chaves: list[str]) -> int:
    """Apaga objetos do bucket. Nunca levanta; sem credenciais devolve 0."""
    if not r2_configurado() or not chaves:
        return 0
    try:
        s3 = _cliente_s3()
        bucket = os.environ["R2_BUCKET"]
        for chave in chaves:
            s3.delete_object(Bucket=bucket, Key=chave)
        return len(chaves)
    except Exception:  # noqa: BLE001
        return 0
```

Em `servicos/proposta.py` (import `normalizar` de `app.dominio.texto`):

```python
def _slug(texto: str) -> str:
    return normalizar(texto).replace(" ", "-")
```

e em `gerar`: `chave = f"Propostas/{_slug(cliente['empresa'])}/{_slug(cliente.get('ref') or 'geral')}/proposta_{proposta_id}.docx"`, mantendo o resto; adicionar `"chave_r2": chave` ao retorno.

- [ ] **Step 3: Rodar e ver passar** — `pytest -q` (suíte inteira verde).
- [ ] **Step 4: Commit** — `git add aut-proposta/app/storage/r2.py aut-proposta/app/servicos/proposta.py aut-proposta/tests/ && git commit -m "feat(proposta): R2 organizado por cliente/projeto e exclusão de objetos"`

---

### Task 2: Backend — repositório de consulta e exclusão de propostas

**Files:**
- Modify: `aut-proposta/app/db/repo_propostas.py`
- Test: `aut-proposta/tests/db/test_repo_propostas.py` (adições)

**Interfaces:**
- Produces:
  - `listar_propostas(conn, cliente: str | None = None) -> list[dict]` — `[{"id", "cliente", "referencia", "data" (iso str), "total" (float), "docx_url"}]`, mais recente primeiro (`ORDER BY p.id DESC`); filtro opcional por nome do cliente (`nome_norm = normalizar(cliente)`).
  - `obter_estrutura_de_proposta(conn, proposta_id) -> dict | None` — reconstrói a `estrutura` (shape do parser: cliente{empresa,ref,contato}, listas de descrições por categoria, `desconto_pct` do registro, `desconto_label=None`, `estrategia="planilha"`, `mostrar_precos_individuais=False`, `_avisos=[]`) a partir de `clientes`+`propostas`+`proposta_itens`. Base do "copiar proposta mudando X".
  - `excluir_proposta(conn, proposta_id) -> bool` — apaga a proposta (itens via cascade) em `conn.transaction()`; True se existia.

- [ ] **Step 1: Testes (falha primeiro)** — adicionar a `tests/db/test_repo_propostas.py`:

```python
from app.db.repo_propostas import (
    excluir_proposta,
    listar_propostas,
    obter_estrutura_de_proposta,
)


def test_listar_propostas_mais_recente_primeiro(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI", "Daniel")
    p1 = salvar_proposta(db, cid, _fechado_exemplo(), referencia="R00")
    p2 = salvar_proposta(db, cid, _fechado_exemplo(), referencia="R01")

    todas = listar_propostas(db)
    assert [p["id"] for p in todas] == [p2, p1]
    assert todas[0]["cliente"] == "GALLI"
    assert todas[0]["referencia"] == "R01"
    assert float(todas[0]["total"]) == 5085.0

    so_galli = listar_propostas(db, cliente="galli")
    assert len(so_galli) == 2
    assert listar_propostas(db, cliente="OUTRO") == []


def test_obter_estrutura_reconstroi_para_copia(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI", "Daniel")
    pid = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Aurora")

    est = obter_estrutura_de_proposta(db, pid)
    assert est["cliente"] == {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"}
    assert est["externas"] == ["Perspectiva Fachada"]
    assert est["internas"] == ["Perspectiva Academia"]
    assert est["desconto_pct"] == 10.0
    assert est["estrategia"] == "planilha"
    assert obter_estrutura_de_proposta(db, 99999) is None


def test_excluir_proposta(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    pid = salvar_proposta(db, cid, _fechado_exemplo())
    assert excluir_proposta(db, pid) is True
    assert excluir_proposta(db, pid) is False
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM proposta_itens WHERE proposta_id=%s", (pid,))
        assert cur.fetchone()[0] == 0
```

Run: `pytest tests/db/test_repo_propostas.py -v` → FAIL (ImportError).

- [ ] **Step 2: Implementar** — ao final de `repo_propostas.py`:

```python
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
```

- [ ] **Step 3: Rodar e ver passar** — `pytest -q`.
- [ ] **Step 4: Commit** — `git add aut-proposta/app/db/repo_propostas.py aut-proposta/tests/db/test_repo_propostas.py && git commit -m "feat(proposta): consulta, reconstrução p/ cópia e exclusão de propostas"`

---

### Task 3: Backend — endpoints de histórico e exclusão

**Files:**
- Modify: `aut-proposta/app/api/main.py`
- Test: `aut-proposta/tests/api/test_api.py` (adições)

**Interfaces:**
- Produces:
  - `GET /propostas?cliente=` (auth) → `{"propostas": [ ...listar_propostas..., "download": "/propostas/{id}/docx", "pdf": "/propostas/{id}/pdf" ]}`.
  - `DELETE /propostas/{id}` (auth) → apaga NEON via `excluir_proposta`; apaga R2 via `excluir_objetos` (chaves derivadas: se `docx_url` contém `/Propostas/`, extrai a chave a partir de `Propostas/`; senão tenta o padrão legado `propostas/proposta_{id}.docx`); remove `PROPOSTAS_DIR/proposta_{id}.docx` e `.pdf` locais se existirem; → `{"excluida": id}`; 404 se não existia.

- [ ] **Step 1: Testes (falha primeiro)** — adicionar a `tests/api/test_api.py`:

```python
def test_listar_propostas_endpoint(cliente_api):
    r0 = cliente_api.post("/propostas", json={"texto": TEXTO}, headers=HEAD)
    pid = r0.json()["proposta_id"]
    r = cliente_api.get("/propostas", headers=HEAD)
    assert r.status_code == 200
    lista = r.json()["propostas"]
    assert lista[0]["id"] == pid
    assert lista[0]["cliente"] == "GALLI"
    assert lista[0]["download"] == f"/propostas/{pid}/docx"
    r2_ = cliente_api.get("/propostas", params={"cliente": "NAOEXISTE"}, headers=HEAD)
    assert r2_.json()["propostas"] == []


def test_excluir_proposta_endpoint(cliente_api, monkeypatch):
    chaves_apagadas = []
    monkeypatch.setattr("app.api.main.excluir_objetos",
                        lambda chaves: chaves_apagadas.extend(chaves) or len(chaves))
    r0 = cliente_api.post("/propostas", json={"texto": TEXTO}, headers=HEAD)
    pid = r0.json()["proposta_id"]

    r = cliente_api.delete(f"/propostas/{pid}", headers=HEAD)
    assert r.status_code == 200
    assert r.json() == {"excluida": pid}
    assert any(str(pid) in c for c in chaves_apagadas)

    assert cliente_api.delete(f"/propostas/{pid}", headers=HEAD).status_code == 404
    assert cliente_api.get(f"/propostas/{pid}/docx", headers=HEAD).status_code == 404
```

Run: `pytest tests/api -v` → FAIL.

- [ ] **Step 2: Implementar** — em `main.py` (imports: `listar_propostas`, `excluir_proposta` de `app.db.repo_propostas`; `excluir_objetos` de `app.storage.r2`):

```python
@app.get("/propostas", dependencies=[Depends(verificar_token)])
def rota_listar(cliente: str | None = None):
    conn = _abrir_conn()
    try:
        propostas = listar_propostas(conn, cliente)
    finally:
        _fechar_conn(conn)
    for p in propostas:
        p["download"] = f"/propostas/{p['id']}/docx"
        p["pdf"] = f"/propostas/{p['id']}/pdf"
    return {"propostas": propostas}


def _chaves_r2_da_proposta(docx_url: str | None, proposta_id: int) -> list[str]:
    if docx_url and "/Propostas/" in docx_url:
        chave = "Propostas/" + docx_url.split("/Propostas/", 1)[1]
    else:
        chave = f"propostas/proposta_{proposta_id}.docx"  # padrão legado
    return [chave]


@app.delete("/propostas/{proposta_id}", dependencies=[Depends(verificar_token)])
def rota_excluir(proposta_id: int):
    conn = _abrir_conn()
    try:
        info = listar_propostas(conn)  # pequena; pega docx_url antes de apagar
        alvo = next((p for p in info if p["id"] == proposta_id), None)
        if alvo is None or not excluir_proposta(conn, proposta_id):
            raise HTTPException(404, "Proposta não encontrada")
    finally:
        _fechar_conn(conn)
    excluir_objetos(_chaves_r2_da_proposta(alvo["docx_url"], proposta_id))
    for ext in (".docx", ".pdf"):
        arq = _dir_saida() / f"proposta_{proposta_id}{ext}"
        if arq.exists():
            arq.unlink()
    return {"excluida": proposta_id}
```

Nota: se preferir evitar `listar_propostas(conn)` completo, um SELECT direto do `docx_url` por id é aceitável — mantenha o comportamento.

- [ ] **Step 3: Rodar e ver passar** — `pytest -q`.
- [ ] **Step 4: Commit** — `git add aut-proposta/app/api/main.py aut-proposta/tests/api/test_api.py && git commit -m "feat(proposta): endpoints de histórico e exclusão (NEON+R2+local)"`

---

### Task 4: Backend — chat conversacional com ferramentas (OpenAI tools)

**Files:**
- Create: `aut-proposta/app/ia/chat.py`
- Modify: `aut-proposta/app/api/main.py` (rota `POST /chat`)
- Test: `aut-proposta/tests/ia/test_chat.py`, 1 teste em `tests/api/test_api.py`

**Interfaces:**
- Consumes: `levantar`, `listar_propostas`, `obter_estrutura_de_proposta`, OpenAI (`OPENAI_MODEL`).
- Produces:
  - `app.ia.chat.responder(conn, mensagens: list[dict]) -> dict` — `{"mensagem": str, "quick_replies": list[str], "levantamento": dict | None}`.
  - `app.ia.chat._chamar_modelo(mensagens_llm, tools) -> objeto` — isolado para monkeypatch (devolve o objeto `message` da OpenAI: `.content`, `.tool_calls`).
  - `POST /chat` (auth) — corpo `{"mensagens": [...]}`; resposta = retorno de `responder`.

**Comportamento:**
- `mensagens == []` → saudação fixa SEM chamar a IA: `{"mensagem": "Oi, tudo bem? O que vamos fazer hoje?", "quick_replies": ["Nova proposta", "Consultar cliente", "Copiar proposta anterior"], "levantamento": null}`.
- Com mensagens: system prompt (persona + regras) + histórico → loop de tool-calls (máx. 5 iterações): a IA pode chamar `precificar_proposta(estrutura)`, `listar_propostas_cliente(cliente)`, `carregar_proposta(proposta_id)`; resultados voltam como `role: "tool"`; o último `levantamento` produzido por `precificar_proposta` é devolvido ao front.
- Sem `OPENAI_API_KEY`/exceção → mensagem de indisponibilidade (constraint global), nunca 500.

- [ ] **Step 1: Testes (falha primeiro)** — `aut-proposta/tests/ia/test_chat.py`:

```python
"""Testes do chat com o modelo mockado (sem rede)."""
import json
from types import SimpleNamespace

import pytest

from app.db.schema import aplicar_schema
from app.ia import chat
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(nome, argumentos, id_="tc1"):
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=nome, arguments=json.dumps(argumentos))
    )


ESTRUTURA = {
    "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
    "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
    "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
    "mostrar_precos_individuais": False, "_avisos": [],
}


def test_conversa_vazia_da_saudacao_sem_ia(db, monkeypatch):
    def _nunca(*a, **kw):
        raise AssertionError("não deveria chamar o modelo")
    monkeypatch.setattr(chat, "_chamar_modelo", _nunca)
    out = chat.responder(db, [])
    assert "Oi, tudo bem?" in out["mensagem"]
    assert out["quick_replies"] == ["Nova proposta", "Consultar cliente",
                                    "Copiar proposta anterior"]
    assert out["levantamento"] is None


def test_ia_precifica_via_ferramenta(db, monkeypatch):
    aplicar_schema(db)
    semear_precos(db)
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta", {"estrutura": ESTRUTURA})]),
        _msg(content="Fechado! Fachada da GALLI dá R$3.000,00. Gero a proposta?"),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    monkeypatch.setenv("OPENAI_API_KEY", "fake")

    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI, fachada"}])
    assert out["levantamento"] is not None
    assert out["levantamento"]["fechado"]["orcamento"]["subtotal"] == 3000
    assert "3.000" in out["mensagem"]


def test_sem_chave_nao_quebra(db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert "Texto direto" in out["mensagem"]
    assert out["levantamento"] is None


def test_excecao_do_modelo_nao_quebra(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    def _explode(*a, **kw):
        raise RuntimeError("api fora")
    monkeypatch.setattr(chat, "_chamar_modelo", _explode)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert out["levantamento"] is None
    assert "Texto direto" in out["mensagem"]
```

Em `tests/api/test_api.py` adicionar:

```python
def test_chat_endpoint_saudacao(cliente_api):
    r = cliente_api.post("/chat", json={"mensagens": []}, headers=HEAD)
    assert r.status_code == 200
    assert "Oi, tudo bem?" in r.json()["mensagem"]
```

Run: `pytest tests/ia/test_chat.py tests/api -v` → FAIL (app.ia.chat inexistente).

- [ ] **Step 2: Implementar `chat.py`**:

```python
"""Chat conversacional da proposta: OpenAI com ferramentas internas.

A IA conduz a conversa (descontraída, pergunta o que falta, aceita tudo de
uma vez) e usa ferramentas para QUALQUER número: precificar, listar
propostas do cliente e carregar proposta antiga para copiar. Stateless — o
front manda o histórico inteiro a cada rodada.
"""
from __future__ import annotations

import json
import os
from typing import Any

import psycopg

from app.db.repo_propostas import listar_propostas, obter_estrutura_de_proposta
from app.servicos.proposta import levantar

SAUDACAO = "Oi, tudo bem? O que vamos fazer hoje?"
QUICK_REPLIES = ["Nova proposta", "Consultar cliente", "Copiar proposta anterior"]
MSG_SEM_IA = ("O chat precisa da IA e ela está indisponível agora — "
              "use a aba 'Texto direto', que funciona sem internet da IA.")
MAX_RODADAS = 5

SYSTEM_PROMPT = """Você é o assistente de propostas da Flying Studio. Tom descontraído,
direto e simpático, em português. Conduza a conversa para montar uma proposta:
precisa de construtora/incorporadora (cliente), empreendimento (ref), A/C (quem
recebe) e os itens (externas/internas/plantas). O usuário pode mandar tudo de uma
vez ou aos poucos — pergunte SÓ o que faltar, uma coisa por vez.

REGRAS INEGOCIÁVEIS:
- Você NUNCA inventa nem calcula preço/valor. Todo número vem das ferramentas.
- Para precificar (mesmo parcial), chame precificar_proposta com a estrutura.
- Para consultar propostas antigas de um cliente, chame listar_propostas_cliente.
- Para copiar uma proposta mudando algo, chame carregar_proposta, ajuste a
  estrutura conforme o pedido e chame precificar_proposta.
- Depois de precificar, resuma os valores devolvidos e diga que o preview ao lado
  foi atualizado; se não houver pendências, diga que é só clicar em Gerar.
"""

FERRAMENTAS = [
    {"type": "function", "function": {
        "name": "precificar_proposta",
        "description": "Precifica a estrutura da proposta (preços oficiais/histórico). "
                       "Devolve valores, totais e pendências obrigatórias.",
        "parameters": {"type": "object", "properties": {"estrutura": {"type": "object"}},
                       "required": ["estrutura"]}}},
    {"type": "function", "function": {
        "name": "listar_propostas_cliente",
        "description": "Lista as propostas já feitas para um cliente (id, projeto, data, total).",
        "parameters": {"type": "object", "properties": {"cliente": {"type": "string"}},
                       "required": ["cliente"]}}},
    {"type": "function", "function": {
        "name": "carregar_proposta",
        "description": "Carrega a estrutura completa de uma proposta antiga pelo id, "
                       "para copiar/ajustar e depois precificar.",
        "parameters": {"type": "object", "properties": {"proposta_id": {"type": "integer"}},
                       "required": ["proposta_id"]}}},
]


def _chamar_modelo(mensagens_llm: list[dict], tools: list[dict]):
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=mensagens_llm,
        tools=tools,
        temperature=0.4,
    )
    return resp.choices[0].message


def _executar_ferramenta(conn: psycopg.Connection, nome: str, args: dict) -> tuple[str, dict | None]:
    """Devolve (resultado_json_para_a_ia, levantamento_ou_None)."""
    if nome == "precificar_proposta":
        lev = levantar(conn, args["estrutura"])
        from app.api.main import _pendencias  # mesma regra de pendências da API
        lev_out = {
            "estrutura": args["estrutura"],
            "fechado": lev["fechado"],
            "estrategia_usada": lev["estrategia_usada"],
            "avisos": lev["avisos"],
            "pendencias": _pendencias(args["estrutura"], lev["fechado"]),
        }
        resumo = {
            "subtotal": lev["fechado"]["financeiro"]["subtotal"],
            "total": lev["fechado"]["financeiro"]["total"],
            "total_imagens": lev["fechado"]["orcamento"]["total_imagens"],
            "pendencias": lev_out["pendencias"],
            "avisos": lev["avisos"],
        }
        return json.dumps(resumo, ensure_ascii=False), lev_out
    if nome == "listar_propostas_cliente":
        return json.dumps(listar_propostas(conn, args["cliente"]), ensure_ascii=False), None
    if nome == "carregar_proposta":
        est = obter_estrutura_de_proposta(conn, int(args["proposta_id"]))
        return json.dumps(est, ensure_ascii=False), None
    return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), None


def responder(conn: psycopg.Connection, mensagens: list[dict]) -> dict[str, Any]:
    if not mensagens:
        return {"mensagem": SAUDACAO, "quick_replies": QUICK_REPLIES, "levantamento": None}
    if not os.getenv("OPENAI_API_KEY"):
        return {"mensagem": MSG_SEM_IA, "quick_replies": [], "levantamento": None}

    llm: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + list(mensagens)
    levantamento: dict | None = None
    try:
        for _ in range(MAX_RODADAS):
            msg = _chamar_modelo(llm, FERRAMENTAS)
            if not getattr(msg, "tool_calls", None):
                return {"mensagem": msg.content or "", "quick_replies": [],
                        "levantamento": levantamento}
            llm.append({"role": "assistant", "content": msg.content,
                        "tool_calls": [
                            {"id": tc.id, "type": "function",
                             "function": {"name": tc.function.name,
                                          "arguments": tc.function.arguments}}
                            for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                resultado, lev = _executar_ferramenta(
                    conn, tc.function.name, json.loads(tc.function.arguments))
                if lev is not None:
                    levantamento = lev
                llm.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
        return {"mensagem": "Precisei de muitas etapas — pode repetir de forma mais direta?",
                "quick_replies": [], "levantamento": levantamento}
    except Exception:  # noqa: BLE001 — IA indisponível nunca derruba o chat
        return {"mensagem": MSG_SEM_IA, "quick_replies": [], "levantamento": None}
```

Rota em `main.py`:

```python
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
```

- [ ] **Step 3: Rodar e ver passar (suíte inteira)** — `pytest -q`.
- [ ] **Step 4: Commit** — `git add aut-proposta/app/ia/chat.py aut-proposta/app/api/main.py aut-proposta/tests/ && git commit -m "feat(proposta): chat conversacional com ferramentas (IA nunca produz número)"`

---

### Task 5: Hub — aba Histórico (lista, download, exclusão com confirmação)

**Files (no worktree do hub):**
- Create: `src/components/agents/proposta/HistoricoPainel.tsx`
- Modify: `src/components/agents/proposta/types.ts` (tipo `PropostaListada`)
- Modify: `src/components/agents/proposta/useProposta.ts` (métodos `listarHistorico`, `excluirProposta`)
- Test: `src/components/agents/proposta/__tests__/HistoricoPainel.test.tsx`

**Interfaces:**
- `PropostaListada = { id: number; cliente: string; referencia: string | null; data: string; total: number; docx_url: string | null; download: string; pdf: string }`.
- Hook: `listarHistorico(cliente?)` → GET `/api/tools/proposta/propostas`; `excluirProposta(id)` → DELETE, e recarrega a lista. Estado novo: `historico: PropostaListada[] | null`.
- UI: tabela (cliente, projeto, data, total BRL, ações: baixar PDF, baixar .docx, excluir); campo de filtro por cliente; excluir abre confirmação inline ("Excluir a proposta #N de CLIENTE? Isso apaga o arquivo do Cloudflare também." + botões Confirmar/Cancelar) antes de chamar.

- [ ] **Step 1: Teste (falha primeiro)** — `__tests__/HistoricoPainel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { HistoricoPainel } from '../HistoricoPainel'

const LISTA = [
  { id: 7, cliente: 'GALLI', referencia: 'Aurora', data: '2026-07-19',
    total: 5085, docx_url: null, download: '/propostas/7/docx', pdf: '/propostas/7/pdf' },
]

describe('HistoricoPainel', () => {
  it('lista propostas com links de download', () => {
    render(<HistoricoPainel propostas={LISTA} onExcluir={jest.fn()} onFiltrar={jest.fn()} carregando={false} />)
    expect(screen.getByText('GALLI')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s?5\.085,00/)).toBeInTheDocument()
    expect(screen.getByLabelText('Baixar PDF da proposta 7'))
      .toHaveAttribute('href', '/api/tools/proposta/propostas/7/pdf')
  })

  it('exclusão exige confirmação', () => {
    const onExcluir = jest.fn()
    render(<HistoricoPainel propostas={LISTA} onExcluir={onExcluir} onFiltrar={jest.fn()} carregando={false} />)
    fireEvent.click(screen.getByLabelText('Excluir proposta 7'))
    expect(onExcluir).not.toHaveBeenCalled()          // ainda não!
    fireEvent.click(screen.getByText('Confirmar exclusão'))
    expect(onExcluir).toHaveBeenCalledWith(7)
  })
})
```

Run: `npx jest src/components/agents/proposta --silent` → FAIL.

- [ ] **Step 2: Implementar** — `HistoricoPainel.tsx` (props `{propostas, onExcluir, onFiltrar, carregando}`; estado local `confirmando: number | null`; estilos dos cards/tabela do hub; datas `new Date(data).toLocaleDateString('pt-BR')`; total com `toLocaleString('pt-BR', {style:'currency',currency:'BRL'})`; links `href={'/api/tools/proposta' + p.pdf}` e `.download`; aria-labels exatamente como no teste). Hook: adicionar

```ts
const listarHistorico = useCallback((cliente?: string) =>
  executar(async () => {
    const q = cliente ? `?cliente=${encodeURIComponent(cliente)}` : ''
    const resp = await fetch(`${BASE}/propostas${q}`)
    if (!resp.ok) throw new Error(`Erro ${resp.status}`)
    setHistorico((await resp.json()).propostas)
  }), [executar])

const excluirProposta = useCallback((id: number) =>
  executar(async () => {
    const resp = await fetch(`${BASE}/propostas/${id}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`Erro ${resp.status}`)
    setHistorico((h) => (h ?? []).filter((p) => p.id !== id))
  }), [executar])
```

- [ ] **Step 3: Rodar e ver passar** — jest do diretório + `npm run build`.
- [ ] **Step 4: Commit** — `git add src/components/agents/proposta/ && git commit -m "feat(proposta): aba de histórico com download e exclusão confirmada"`

---

### Task 6: Hub — aba Chat (bolhas, quick replies, preview integrado)

**Files (no worktree do hub):**
- Create: `src/components/agents/proposta/ChatPainel.tsx`
- Modify: `src/components/agents/proposta/types.ts` (`MensagemChat`, `RespostaChat`)
- Modify: `src/components/agents/proposta/useProposta.ts` (`conversar(mensagens)`)
- Modify: `src/components/agents/proposta/PropostaAgent.tsx` (abas Chat | Texto direto | Histórico)
- Test: `src/components/agents/proposta/__tests__/ChatPainel.test.tsx`

**Interfaces:**
- `MensagemChat = { role: 'user' | 'assistant'; content: string }`; `RespostaChat = { mensagem: string; quick_replies: string[]; levantamento: Levantamento | null }`.
- Hook `conversar(mensagens)` → POST `/api/tools/proposta/chat`; quando a resposta traz `levantamento`, também faz `setLevantamento` (o preview à direita atualiza sozinho).
- `ChatPainel` props `{mensagens, quickReplies, onEnviar(texto), carregando}`: bolhas (user à direita roxa, assistant à esquerda cinza), quick replies como chips clicáveis (enviam o texto), input com Enter para enviar, auto-scroll.
- `PropostaAgent`: estado `aba: 'chat' | 'texto' | 'historico'`; monta o chat com a saudação inicial (chama `conversar([])` ao abrir a aba); layout do chat: grid 2 colunas com `PreviewPainel` à direita quando houver `levantamento` (o botão Gerar existente serve igual); aba Texto = `EntradaPainel` atual; aba Histórico = Task 5 (carrega ao entrar na aba).

- [ ] **Step 1: Teste (falha primeiro)** — `__tests__/ChatPainel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatPainel } from '../ChatPainel'

describe('ChatPainel', () => {
  it('mostra bolhas e envia com Enter', () => {
    const onEnviar = jest.fn()
    render(<ChatPainel
      mensagens={[{ role: 'assistant', content: 'Oi, tudo bem? O que vamos fazer hoje?' }]}
      quickReplies={['Nova proposta']}
      onEnviar={onEnviar}
      carregando={false}
    />)
    expect(screen.getByText(/Oi, tudo bem\?/)).toBeInTheDocument()
    const input = screen.getByPlaceholderText(/Escreva aqui/)
    fireEvent.change(input, { target: { value: 'Cliente GALLI' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onEnviar).toHaveBeenCalledWith('Cliente GALLI')
  })

  it('quick reply envia o texto do chip', () => {
    const onEnviar = jest.fn()
    render(<ChatPainel mensagens={[]} quickReplies={['Nova proposta']} onEnviar={onEnviar} carregando={false} />)
    fireEvent.click(screen.getByText('Nova proposta'))
    expect(onEnviar).toHaveBeenCalledWith('Nova proposta')
  })
})
```

Run: jest → FAIL.

- [ ] **Step 2: Implementar** — `ChatPainel.tsx` (bolhas com `max-w-[80%]`, user `bg-brand-purple text-white ml-auto`, assistant `bg-white dark:bg-[#0F0F0F] border`; chips `rounded-full border border-brand-purple text-brand-purple px-3 py-1 text-xs hover:bg-brand-purple/10`; input placeholder `"Escreva aqui… (ex.: proposta para GALLI, 3 externas)"`; auto-scroll via `useRef`+`useEffect`). Hook `conversar`:

```ts
const conversar = useCallback((mensagens: MensagemChat[]) =>
  executar(async () => {
    const resp = await postJson<RespostaChat>('/chat', { mensagens })
    setChat({ mensagens, resposta: resp })
    if (resp.levantamento) setLevantamento(resp.levantamento)
  }), [executar])
```

(estado `chat: {mensagens, resposta} | null`; `PropostaAgent` mantém a lista de mensagens: ao enviar, anexa `{role:'user',content}` + depois `{role:'assistant',content:resposta.mensagem}`.)

`PropostaAgent`: barra de abas no topo (botões com `aria-pressed`, estilos do hub); aba padrão `chat`; ao montar a aba chat sem mensagens → `conversar([])` para receber a saudação.

- [ ] **Step 3: Rodar e ver passar** — jest do diretório (esperado: todos os testes do agente) + `npm run build`.
- [ ] **Step 4: Verificação manual local (obrigatória)** — serviço local + `npm run dev`: abrir a ferramenta → saudação + chips; "Cliente GALLI" → IA pergunta o projeto; responder aos poucos até precificar (preview atualiza); "quanto foi a última proposta da GALLI?" → resposta com valores; "copia a proposta X com 10% de desconto" → preview atualizado; aba Histórico → lista, baixar PDF, excluir com confirmação. Registrar no relatório.
- [ ] **Step 5: Commit** — `git add src/components/agents/proposta/ && git commit -m "feat(proposta): chat conversacional com preview integrado e abas"`

---

### Task 7: Verificação de produção (controlador + usuário)

Sem código novo. Após merges dos dois PRs: Railway redeploya o serviço; conferir em produção via hub: saudação do chat, fluxo aos poucos, consulta de cliente, cópia com ajuste, histórico com download e exclusão (criar e excluir uma proposta de teste; conferir que sumiu do NEON e do R2 — a chave nova `Propostas/...`). Registrar no ledger.

---

## Self-Review

**Cobertura dos pedidos do usuário (2026-07-19):**
1. Chat livre e descontraído, saudação fixa, opções pré-fixadas, aceita aos poucos OU tudo direto → Task 4 (persona + tools + stateless) e Task 6 (bolhas + chips). ✔
2. Chat de consultas (propostas anteriores, valores, copiar mudando X) → ferramentas `listar_propostas_cliente`/`carregar_proposta` (Task 4) sobre os repositórios da Task 2. ✔
3. R2 organizado `Propostas/Cliente/Projeto/propostaNN` → Task 1 (só novas, decisão do usuário). ✔
4. Histórico visível no Workspace com re-download do docx (e PDF) → Tasks 3 + 5. ✔
5. Exclusão sem ir ao banco (limpa Cloudflare junto) → Tasks 2 + 3 (DELETE NEON+R2+local) + confirmação na UI (Task 5, decisão: definitiva). ✔
6. (Assinatura sem nome do cliente — já aplicado fora deste plano, commit 211ad92.)

**Placeholders:** nenhum TBD; código presente em todos os steps de código.

**Consistência de nomes/tipos:** `responder` devolve `levantamento` no MESMO shape do `/levantamento` (reuso de `_pendencias` da API); `PropostaListada` espelha `rota_listar` (incl. `download`/`pdf`); `conversar` reusa `postJson`/`setLevantamento` existentes; `excluir_objetos(chaves)` consumido por `rota_excluir`; `_slug` usa `normalizar` (não reimplementa); `obter_estrutura_de_proposta` devolve exatamente o shape que `levantar`/`precificar_proposta` consomem. ✔

**Riscos anotados para revisores:** import tardio `from app.api.main import _pendencias` dentro de `chat.py` (ciclo main→chat→main é evitado porque o import de `chat` na rota também é tardio) — se preferirem, mover `_pendencias` para `app/servicos/proposta.py` é refactor aceitável, atualizando os dois usos; contrato OpenAI tool-calls mockado por `SimpleNamespace` nos testes deve casar com o SDK real (verificação manual da Task 6 cobre).
