# Automação de Proposta — Plano 2: Persistência NEON + Histórico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistir preços, clientes e propostas no NEON (Postgres) e habilitar o 2º levantamento (por histórico do cliente), mantendo o núcleo `app/dominio/` puro e inalterado.

**Architecture:** Novo pacote `app/db/` (psycopg3) com conexão, schema e repositórios; script de seed que popula a tabela de preços a partir do JSON do Plano 1; e `app/historico/` que compõe o domínio puro com o histórico vindo do banco. Produção usa NEON; testes usam um Postgres local via Docker. **NEON é a única fonte de preços em runtime** — o JSON é apenas insumo de seed.

**Tech Stack:** Python 3.12+, psycopg3, Postgres 16 (NEON em prod, Docker local em teste), pytest.

## Roadmap dos planos (contexto)

Plano 2 de 4. (1) Núcleo determinístico ✅ concluído. **(2) Persistência NEON + histórico (este).** (3) docx + IA + API. (4) UI no hub.

## Global Constraints

- Python **3.12+**; Postgres **16**.
- **`app/dominio/` permanece puro e INALTERADO** — nenhum arquivo de `app/dominio/` pode importar `psycopg`, rede ou banco. Todo código de banco vive em `app/db/`; a composição domínio+histórico vive em `app/historico/`.
- Driver: **psycopg (v3)**. Conexão sempre via DSN de variável de ambiente (`DATABASE_URL` em prod).
- Testes que tocam o banco usam a marca `@pytest.mark.db` e o fixture `db`; conectam ao Postgres de teste via `DATABASE_URL_TEST` (default `postgresql://postgres:postgres@localhost:5432/aut_proposta_test`). Se o banco estiver indisponível, esses testes **pulam** com mensagem clara (não falham silenciosamente), preservando a suíte offline do Plano 1.
- Dinheiro de item é `int`; totais monetários da proposta usam `numeric` no banco.
- Categorias base: `("externas", "internas", "plantas")`.
- Preços: **NEON é a única fonte em runtime**. O JSON `app/dados/precos_planilha.json` é só o insumo do seed. Nenhum caminho de produção lê o JSON.
- Normalização de nomes/descrições reutiliza `app.dominio.texto.normalizar` (não reimplementar).
- Código e comentários em português.
- Lógica de histórico a portar de `Aut_proposta_old/Flying-studio-proposta/flying/historico.py` (métodos `medias_por_categoria`, `tabela_precos_inferida`) e `orcamento.py` (`orcar_pelo_historico`).

---

### Task 1: Infraestrutura de banco (conexão + Docker + fixtures)

**Files:**
- Modify: `aut-proposta/pyproject.toml` (adicionar dep `psycopg[binary]` e marker `db`)
- Create: `aut-proposta/docker-compose.yml`
- Create: `aut-proposta/app/db/__init__.py`
- Create: `aut-proposta/app/db/conexao.py`
- Create: `aut-proposta/tests/conftest.py`
- Test: `aut-proposta/tests/db/__init__.py`, `aut-proposta/tests/db/test_conexao.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `app.db.conexao.get_conn(dsn: str | None = None) -> psycopg.Connection` — abre conexão; `dsn=None` usa `os.environ["DATABASE_URL"]`.
  - Fixture pytest `db` (function-scoped) — devolve uma `psycopg.Connection` já conectada ao Postgres de teste, com schema aplicado (via Task 2) e todas as tabelas truncadas. Pula o teste se o banco estiver indisponível. **Nota:** o fixture chama `aplicar_schema`, criado na Task 2 — implemente o fixture completo já nesta task; os testes que o usam só existem a partir da Task 2, então o import de `aplicar_schema` passa a resolver quando a Task 2 criar `app/db/schema.py`. Para a Task 1 rodar isolada, o fixture importa `aplicar_schema` **dentro** da função (import tardio), e o único teste desta task (`test_conexao`) NÃO usa o fixture `db`.

- [ ] **Step 1: Adicionar dependência e marker ao `pyproject.toml`**

Em `aut-proposta/pyproject.toml`, alterar a lista `dependencies` e a seção `[tool.pytest.ini_options]`:

```toml
dependencies = ["psycopg[binary]>=3.2"]
```

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "db: teste que requer Postgres (usa o fixture db; pula se indisponível)",
]
```

Instalar: a partir de `aut-proposta/`, `pip install -e ".[dev]"`.

- [ ] **Step 2: Criar `docker-compose.yml` para o Postgres de teste**

`aut-proposta/docker-compose.yml`:

```yaml
services:
  db-test:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: aut_proposta_test
    ports:
      - "5432:5432"
```

- [ ] **Step 3: Escrever o teste de conexão (falha primeiro)**

`aut-proposta/tests/db/__init__.py` vazio. `aut-proposta/tests/db/test_conexao.py`:

```python
import os

import psycopg
import pytest

from app.db.conexao import get_conn

DSN_TESTE = os.environ.get(
    "DATABASE_URL_TEST", "postgresql://postgres:postgres@localhost:5432/aut_proposta_test"
)


def test_get_conn_usa_dsn_explicito():
    try:
        conn = get_conn(DSN_TESTE)
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres de teste indisponível ({e}). Suba com: docker compose up -d db-test")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `pytest tests/db/test_conexao.py -v`
Expected: FAIL (ModuleNotFoundError: app.db.conexao).

- [ ] **Step 5: Implementar `conexao.py` e `conftest.py`**

`aut-proposta/app/db/__init__.py` vazio.

`aut-proposta/app/db/conexao.py`:

```python
"""Conexão com o Postgres (NEON em produção, Postgres local em teste)."""
from __future__ import annotations

import os

import psycopg


def get_conn(dsn: str | None = None) -> psycopg.Connection:
    """Abre uma conexão. Se dsn=None, usa a variável DATABASE_URL."""
    dsn = dsn or os.environ["DATABASE_URL"]
    return psycopg.connect(dsn)
```

`aut-proposta/tests/conftest.py`:

```python
"""Fixtures compartilhados dos testes de banco."""
from __future__ import annotations

import os

import psycopg
import pytest

from app.db.conexao import get_conn

DSN_TESTE = os.environ.get(
    "DATABASE_URL_TEST", "postgresql://postgres:postgres@localhost:5432/aut_proposta_test"
)

TABELAS = ("proposta_itens", "propostas", "clientes", "preco_item", "preco_categoria")


@pytest.fixture
def db():
    """Conexão ao Postgres de teste, com schema aplicado e tabelas limpas.

    Pula o teste (não falha) se o banco estiver indisponível.
    """
    from app.db.schema import aplicar_schema  # import tardio: existe a partir da Task 2

    try:
        conn = get_conn(DSN_TESTE)
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres de teste indisponível ({e}). Suba com: docker compose up -d db-test")

    aplicar_schema(conn)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABELAS)} RESTART IDENTITY CASCADE")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 6: Rodar e ver passar**

Pré-requisito: `docker compose up -d db-test` (a partir de `aut-proposta/`). Se o Docker não estiver rodando, o teste PULA (skip) — isso é aceitável para o commit, mas rode com o banco no ar ao menos uma vez.

Run: `pytest tests/db/test_conexao.py -v`
Expected: PASS (1 passed) com o banco no ar, ou SKIP com mensagem clara sem ele. Rode a suíte inteira `pytest` e confirme que os testes do Plano 1 continuam passando (25 passed) e o de banco passa ou pula.

- [ ] **Step 7: Commit**

```bash
git add aut-proposta/pyproject.toml aut-proposta/docker-compose.yml aut-proposta/app/db/ aut-proposta/tests/conftest.py aut-proposta/tests/db/
git commit -m "feat(proposta): infra de banco (psycopg, docker de teste, fixtures)"
```

---

### Task 2: Schema do banco

**Files:**
- Create: `aut-proposta/app/db/schema.sql`
- Create: `aut-proposta/app/db/schema.py`
- Test: `aut-proposta/tests/db/test_schema.py`

**Interfaces:**
- Consumes: `psycopg.Connection`.
- Produces: `app.db.schema.aplicar_schema(conn: psycopg.Connection) -> None` — executa o DDL idempotente (`CREATE TABLE IF NOT EXISTS`) e faz commit. Tabelas: `preco_categoria`, `preco_item`, `clientes`, `propostas`, `proposta_itens`.

- [ ] **Step 1: Criar o DDL**

`aut-proposta/app/db/schema.sql`:

```sql
-- Tabela de preços (fonte da verdade em runtime; semeada do JSON)
CREATE TABLE IF NOT EXISTS preco_categoria (
    categoria         text PRIMARY KEY,
    preco_default     integer NOT NULL,
    descricao_padrao  text NOT NULL
);

CREATE TABLE IF NOT EXISTS preco_item (
    id         serial PRIMARY KEY,
    categoria  text NOT NULL REFERENCES preco_categoria(categoria) ON DELETE CASCADE,
    chave      text NOT NULL,
    descricao  text NOT NULL,
    preco      integer NOT NULL,
    padroes    text[] NOT NULL DEFAULT '{}',
    ordem      integer NOT NULL,
    UNIQUE (categoria, chave)
);

-- Clientes e propostas (histórico)
CREATE TABLE IF NOT EXISTS clientes (
    id         serial PRIMARY KEY,
    nome       text NOT NULL,
    nome_norm  text NOT NULL UNIQUE,
    contato    text,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS propostas (
    id              serial PRIMARY KEY,
    cliente_id      integer NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    referencia      text,
    data            date NOT NULL DEFAULT current_date,
    status          text NOT NULL DEFAULT 'rascunho',
    subtotal        integer NOT NULL,
    desconto_pct    numeric(6,2) NOT NULL DEFAULT 0,
    desconto_valor  numeric(12,2) NOT NULL DEFAULT 0,
    total           numeric(12,2) NOT NULL,
    docx_url        text,
    criado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proposta_itens (
    id           serial PRIMARY KEY,
    proposta_id  integer NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
    categoria    text NOT NULL,
    descricao    text NOT NULL,
    preco        integer NOT NULL,
    origem       text NOT NULL
);
```

- [ ] **Step 2: Escrever o teste (falha primeiro)**

`aut-proposta/tests/db/test_schema.py`:

```python
import pytest

pytestmark = pytest.mark.db

TABELAS_ESPERADAS = {
    "preco_categoria", "preco_item", "clientes", "propostas", "proposta_itens",
}


def test_aplicar_schema_cria_todas_as_tabelas(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existentes = {r[0] for r in cur.fetchall()}
    assert TABELAS_ESPERADAS.issubset(existentes)


def test_aplicar_schema_e_idempotente(db):
    from app.db.schema import aplicar_schema

    # Chamar de novo não deve levantar erro.
    aplicar_schema(db)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM preco_categoria")
        assert cur.fetchone()[0] == 0
```

- [ ] **Step 3: Rodar e ver falhar**

Pré-requisito: `docker compose up -d db-test`.
Run: `pytest tests/db/test_schema.py -v`
Expected: FAIL (ModuleNotFoundError: app.db.schema) — ou SKIP se o banco não estiver no ar (nesse caso, suba o Docker para validar de verdade).

- [ ] **Step 4: Implementar `schema.py`**

`aut-proposta/app/db/schema.py`:

```python
"""Aplicação idempotente do schema do banco."""
from __future__ import annotations

from pathlib import Path

import psycopg

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def aplicar_schema(conn: psycopg.Connection) -> None:
    """Executa o DDL (CREATE TABLE IF NOT EXISTS ...) e faz commit."""
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/db/test_schema.py -v`
Expected: PASS (2 passed) com o banco no ar.

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/app/db/schema.sql aut-proposta/app/db/schema.py aut-proposta/tests/db/test_schema.py
git commit -m "feat(proposta): schema do banco (preços, clientes, propostas)"
```

---

### Task 3: Seed da tabela de preços a partir do JSON

**Files:**
- Create: `aut-proposta/scripts/__init__.py`
- Create: `aut-proposta/scripts/seed_precos.py`
- Test: `aut-proposta/tests/db/test_seed_precos.py`

**Interfaces:**
- Consumes: `psycopg.Connection`, `app/dados/precos_planilha.json`.
- Produces: `scripts.seed_precos.semear_precos(conn: psycopg.Connection) -> dict[str, int]` — trunca e repopula `preco_categoria`/`preco_item` a partir do JSON, faz commit, e devolve `{"categorias": n, "itens": m}` com as contagens inseridas. Cobre apenas as categorias base `("externas","internas","plantas")`.

- [ ] **Step 1: Escrever o teste (falha primeiro)**

`aut-proposta/scripts/__init__.py` vazio. `aut-proposta/tests/db/test_seed_precos.py`:

```python
import pytest

from app.db.schema import aplicar_schema
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_seed_popula_categorias_e_itens(db):
    aplicar_schema(db)
    contagens = semear_precos(db)

    assert contagens["categorias"] == 3
    assert contagens["itens"] >= 3  # ao menos uma linha por categoria base

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM preco_categoria")
        assert cur.fetchone()[0] == 3
        # A categoria 'externas' deve conter a linha de fachada a 3000.
        cur.execute(
            "SELECT preco FROM preco_item WHERE categoria='externas' AND chave='fachada_fotomontagem_voo'"
        )
        assert cur.fetchone()[0] == 3000


def test_seed_e_idempotente(db):
    aplicar_schema(db)
    c1 = semear_precos(db)
    c2 = semear_precos(db)
    assert c1 == c2  # rodar duas vezes não duplica


def test_padroes_sao_lista(db):
    aplicar_schema(db)
    semear_precos(db)
    with db.cursor() as cur:
        cur.execute("SELECT padroes FROM preco_item WHERE categoria='externas' LIMIT 1")
        padroes = cur.fetchone()[0]
    assert isinstance(padroes, list)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/db/test_seed_precos.py -v`
Expected: FAIL (ModuleNotFoundError: scripts.seed_precos).

- [ ] **Step 3: Implementar `seed_precos.py`**

`aut-proposta/scripts/seed_precos.py`:

```python
"""Semeia a tabela de preços no banco a partir do JSON versionado.

Uso avulso (produção): defina DATABASE_URL e rode `python -m scripts.seed_precos`.
O JSON é apenas o insumo do seed — em runtime a fonte da verdade é o banco.
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

from app.db.conexao import get_conn

JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "dados" / "precos_planilha.json"
CATEGORIAS = ("externas", "internas", "plantas")


def semear_precos(conn: psycopg.Connection) -> dict[str, int]:
    with open(JSON_PATH, encoding="utf-8") as f:
        dados = json.load(f)

    n_cat = 0
    n_item = 0
    with conn.cursor() as cur:
        cur.execute("TRUNCATE preco_item, preco_categoria RESTART IDENTITY CASCADE")
        for cat in CATEGORIAS:
            bloco = dados[cat]
            cur.execute(
                "INSERT INTO preco_categoria (categoria, preco_default, descricao_padrao) "
                "VALUES (%s, %s, %s)",
                (cat, bloco["_default"], bloco["_descricao_padrao"]),
            )
            n_cat += 1
            for ordem, linha in enumerate(bloco["tabela"]):
                cur.execute(
                    "INSERT INTO preco_item (categoria, chave, descricao, preco, padroes, ordem) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (cat, linha["chave"], linha["descricao"], linha["preco"],
                     linha["padroes"], ordem),
                )
                n_item += 1
    conn.commit()
    return {"categorias": n_cat, "itens": n_item}


if __name__ == "__main__":
    conn = get_conn()
    try:
        print(semear_precos(conn))
    finally:
        conn.close()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/db/test_seed_precos.py -v`
Expected: PASS (3 passed) com o banco no ar.

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/scripts/ aut-proposta/tests/db/test_seed_precos.py
git commit -m "feat(proposta): seed da tabela de preços a partir do JSON"
```

---

### Task 4: Repositório de preços (NEON → TabelaPrecos)

**Files:**
- Create: `aut-proposta/app/db/repo_precos.py`
- Test: `aut-proposta/tests/db/test_repo_precos.py`

**Interfaces:**
- Consumes: `psycopg.Connection`, `app.dominio.precos.TabelaPrecos`.
- Produces: `app.db.repo_precos.carregar_tabela_precos(conn: psycopg.Connection) -> TabelaPrecos` — lê `preco_categoria` + `preco_item` (ordenado por `ordem`) e devolve uma `TabelaPrecos` com o mesmo formato de `dados` que o construtor espera. É assim que o runtime obtém preços do NEON sem tocar no domínio.

- [ ] **Step 1: Escrever o teste (falha primeiro)**

`aut-proposta/tests/db/test_repo_precos.py`:

```python
import pytest

from app.db.repo_precos import carregar_tabela_precos
from app.db.schema import aplicar_schema
from app.dominio.precos import TabelaPrecos
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def test_tabela_do_banco_classifica_igual_ao_json(db):
    aplicar_schema(db)
    semear_precos(db)

    tabela_db = carregar_tabela_precos(db)
    tabela_json = TabelaPrecos()  # carrega o JSON direto

    # A classificação deve ser idêntica vindo do banco ou do JSON.
    for desc, cat in [
        ("Fachada vista da calçada", "externas"),
        ("Jardim", "externas"),
        ("Academia", "internas"),
        ("Implantação Térreo", "plantas"),
        ("Apartamento Tipo", "plantas"),
    ]:
        assert tabela_db.classificar(desc, cat) == tabela_json.classificar(desc, cat)


def test_ordem_preservada_primeiro_match_vence(db):
    aplicar_schema(db)
    semear_precos(db)
    tabela_db = carregar_tabela_precos(db)
    # "Fachada" tem que bater a linha de fachada (3000), não a diversa (1900).
    assert tabela_db.classificar("Fachada vista da calçada", "externas")["preco"] == 3000
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/db/test_repo_precos.py -v`
Expected: FAIL (ModuleNotFoundError: app.db.repo_precos).

- [ ] **Step 3: Implementar `repo_precos.py`**

`aut-proposta/app/db/repo_precos.py`:

```python
"""Carrega a tabela de preços do banco, montando a estrutura que TabelaPrecos espera."""
from __future__ import annotations

import psycopg

from app.dominio.precos import CATEGORIAS_VALIDAS, TabelaPrecos


def carregar_tabela_precos(conn: psycopg.Connection) -> TabelaPrecos:
    dados: dict = {}
    with conn.cursor() as cur:
        cur.execute("SELECT categoria, preco_default, descricao_padrao FROM preco_categoria")
        for categoria, preco_default, descricao_padrao in cur.fetchall():
            dados[categoria] = {
                "_default": preco_default,
                "_descricao_padrao": descricao_padrao,
                "tabela": [],
            }

        cur.execute(
            "SELECT categoria, chave, descricao, preco, padroes "
            "FROM preco_item ORDER BY categoria, ordem"
        )
        for categoria, chave, descricao, preco, padroes in cur.fetchall():
            dados[categoria]["tabela"].append(
                {"chave": chave, "descricao": descricao, "preco": preco, "padroes": padroes}
            )

    # Garante que as categorias base existam (mesmo que sem linhas).
    for cat in CATEGORIAS_VALIDAS:
        dados.setdefault(cat, {"_default": 0, "_descricao_padrao": "", "tabela": []})

    return TabelaPrecos(dados)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/db/test_repo_precos.py -v`
Expected: PASS (2 passed) com o banco no ar.

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/db/repo_precos.py aut-proposta/tests/db/test_repo_precos.py
git commit -m "feat(proposta): repositório de preços (NEON -> TabelaPrecos)"
```

---

### Task 5: Repositório de clientes e propostas

**Files:**
- Create: `aut-proposta/app/db/repo_propostas.py`
- Test: `aut-proposta/tests/db/test_repo_propostas.py`

**Interfaces:**
- Consumes: `psycopg.Connection`, `app.dominio.texto.normalizar`.
- Produces:
  - `upsert_cliente(conn, nome: str, contato: str | None = None) -> int` — insere ou reencontra o cliente por `nome_norm = normalizar(nome)`; devolve `id`.
  - `salvar_proposta(conn, cliente_id: int, fechado: dict, referencia: str | None = None, docx_url: str | None = None) -> int` — grava uma proposta e seus itens a partir da estrutura devolvida por `dominio.orcamento.fechar_orcamento` (`{"orcamento": {...}, "financeiro": {...}}`); devolve o `id` da proposta.
  - `ultima_proposta_estruturada(conn, cliente_id: int) -> dict | None` — devolve a proposta mais recente do cliente no formato `{cat: {"qtd", "total", "itens": [{"desc", "preco"}]}}` para as categorias base, ou `None` se o cliente não tem proposta.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/db/test_repo_propostas.py`:

```python
import pytest

from app.db.repo_propostas import (
    salvar_proposta,
    ultima_proposta_estruturada,
    upsert_cliente,
)
from app.db.schema import aplicar_schema

pytestmark = pytest.mark.db


def _fechado_exemplo():
    # Espelha a estrutura de dominio.orcamento.fechar_orcamento.
    return {
        "orcamento": {
            "estrategia": "planilha",
            "subtotal": 5650,
            "total_imagens": 3,
            "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                         "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000, "fonte": "planilha:fachada"}]},
            "internas": {"nome": "internas", "qtd": 1, "total": 1750,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1750, "fonte": "planilha:interna_diversa"}]},
            "plantas": {"nome": "plantas", "qtd": 1, "total": 1200,
                        "itens": [{"descricao": "Planta Humanizada Tipo", "preco": 1200, "fonte": "planilha:planta_tipo"}]},
        },
        "financeiro": {"subtotal": 5650, "desconto_pct": 10.0, "desconto_valor": 565.0,
                       "total": 5085.0, "rotulo": "10% parceria"},
    }


def test_upsert_cliente_idempotente(db):
    aplicar_schema(db)
    id1 = upsert_cliente(db, "GALLI", "Daniel Pucci")
    id2 = upsert_cliente(db, "galli")  # mesmo cliente, caixa diferente
    assert id1 == id2


def test_salvar_proposta_grava_itens(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    pid = salvar_proposta(db, cid, _fechado_exemplo(), referencia="Teste R00")

    with db.cursor() as cur:
        cur.execute("SELECT subtotal, total, desconto_pct FROM propostas WHERE id=%s", (pid,))
        subtotal, total, desconto_pct = cur.fetchone()
        assert subtotal == 5650
        assert float(total) == 5085.0
        assert float(desconto_pct) == 10.0
        cur.execute("SELECT count(*) FROM proposta_itens WHERE proposta_id=%s", (pid,))
        assert cur.fetchone()[0] == 3


def test_ultima_proposta_estruturada(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "GALLI")
    salvar_proposta(db, cid, _fechado_exemplo())

    ult = ultima_proposta_estruturada(db, cid)
    assert ult["externas"]["qtd"] == 1
    assert ult["externas"]["total"] == 3000
    assert ult["externas"]["itens"][0] == {"desc": "Perspectiva Fachada", "preco": 3000}


def test_ultima_proposta_none_sem_proposta(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "NOVO CLIENTE")
    assert ultima_proposta_estruturada(db, cid) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/db/test_repo_propostas.py -v`
Expected: FAIL (ModuleNotFoundError: app.db.repo_propostas).

- [ ] **Step 3: Implementar `repo_propostas.py`**

`aut-proposta/app/db/repo_propostas.py`:

```python
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
        cur.execute(
            "INSERT INTO clientes (nome, nome_norm, contato) VALUES (%s, %s, %s) RETURNING id",
            (nome, nome_norm, contato),
        )
        novo_id = cur.fetchone()[0]
    conn.commit()
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
    with conn.cursor() as cur:
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
    conn.commit()
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
            "SELECT categoria, descricao, preco FROM proposta_itens WHERE proposta_id = %s",
            (pid,),
        )
        for categoria, descricao, preco in cur.fetchall():
            if categoria in out:
                out[categoria]["itens"].append({"desc": descricao, "preco": preco})
                out[categoria]["qtd"] += 1
                out[categoria]["total"] += preco
    return out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/db/test_repo_propostas.py -v`
Expected: PASS (4 passed) com o banco no ar.

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/db/repo_propostas.py aut-proposta/tests/db/test_repo_propostas.py
git commit -m "feat(proposta): repositório de clientes e propostas"
```

---

### Task 6: Histórico + 2º levantamento (orçamento por histórico)

**Files:**
- Create: `aut-proposta/app/historico/__init__.py`
- Create: `aut-proposta/app/historico/historico.py`
- Create: `aut-proposta/app/historico/orcamento_historico.py`
- Test: `aut-proposta/tests/historico/__init__.py`, `aut-proposta/tests/historico/test_orcamento_historico.py`

**Interfaces:**
- Consumes: `psycopg.Connection`, `app.db.repo_propostas`, `app.dominio.{orcamento,precos,texto}`.
- Produces:
  - `app.historico.historico.Historico(conn)` com:
    - `tem_cliente(nome: str) -> bool`
    - `medias_por_categoria(nome: str) -> dict[str, float] | None`
    - `tabela_precos_inferida(nome: str) -> dict[str, dict[str, int]] | None`
  - `app.historico.orcamento_historico.orcar_pelo_historico(historico: Historico, cliente: str, descricoes: dict[str, list[str]], tabela: TabelaPrecos) -> Orcamento | None` — devolve `None` se o cliente não tem histórico; senão reaplica os preços do último projeto (item exato → similar → média da categoria → planilha), com `estrategia="historico:<cliente>"`.

**Nota de arquitetura:** estes módulos ficam em `app/historico/` (não em `app/dominio/`), pois compõem o domínio puro com dados do banco — mantendo a pureza de `app/dominio/`.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/historico/__init__.py` vazio. `aut-proposta/tests/historico/test_orcamento_historico.py`:

```python
import pytest

from app.db.repo_propostas import salvar_proposta, upsert_cliente
from app.db.schema import aplicar_schema
from app.historico.historico import Historico
from app.historico.orcamento_historico import orcar_pelo_historico
from app.dominio.precos import TabelaPrecos

pytestmark = pytest.mark.db

DADOS = {
    "externas": {"_default": 1900, "_descricao_padrao": "Perspectiva Externa",
                 "tabela": [{"chave": "externa_diversa", "descricao": "Perspectiva Externa",
                             "preco": 1900, "padroes": [".*"]}]},
    "internas": {"_default": 1750, "_descricao_padrao": "Perspectiva Interna",
                 "tabela": [{"chave": "interna_diversa", "descricao": "Perspectiva Interna",
                             "preco": 1750, "padroes": [".*"]}]},
    "plantas": {"_default": 1200, "_descricao_padrao": "Planta Humanizada",
                "tabela": [{"chave": "planta_tipo", "descricao": "Planta Humanizada Tipo",
                            "preco": 1200, "padroes": [".*"]}]},
}


def _proposta_premium():
    # Cliente que pagou premium: interna a 1800 (acima da tabela 1750).
    return {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 1800, "total_imagens": 1,
            "externas": {"nome": "externas", "qtd": 0, "total": 0, "itens": []},
            "internas": {"nome": "internas", "qtd": 1, "total": 1800,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1800, "fonte": "manual"}]},
            "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []},
        },
        "financeiro": {"subtotal": 1800, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 1800.0, "rotulo": ""},
    }


def test_sem_cliente_devolve_none(db):
    aplicar_schema(db)
    hist = Historico(db)
    assert orcar_pelo_historico(hist, "INEXISTENTE", {"internas": ["Academia"]}, TabelaPrecos(DADOS)) is None


def test_reaplica_preco_do_historico_item_exato(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, _proposta_premium())

    hist = Historico(db)
    orc = orcar_pelo_historico(hist, "BRNPAR", {"internas": ["Perspectiva Academia"]}, TabelaPrecos(DADOS))
    assert orc is not None
    assert orc.estrategia == "historico:BRNPAR"
    # Reaplica 1800 (histórico), não 1750 (tabela).
    assert orc.internas.itens[0].preco == 1800


def test_item_novo_cai_para_media_ou_planilha(db):
    aplicar_schema(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, _proposta_premium())

    hist = Historico(db)
    # Descrição de externas que o cliente nunca teve -> média (0 itens) -> planilha 1900.
    orc = orcar_pelo_historico(hist, "BRNPAR", {"externas": ["Jardim"]}, TabelaPrecos(DADOS))
    assert orc.externas.itens[0].preco == 1900
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/historico/test_orcamento_historico.py -v`
Expected: FAIL (ModuleNotFoundError: app.historico.historico).

- [ ] **Step 3: Implementar `historico.py`**

`aut-proposta/app/historico/__init__.py` vazio.

`aut-proposta/app/historico/historico.py`:

```python
"""Histórico de propostas por cliente, lido do banco.

Calcula o 'preço do último projeto do mesmo cliente' — base do 2º levantamento.
"""
from __future__ import annotations

import psycopg

from app.db.repo_propostas import ultima_proposta_estruturada, upsert_cliente
from app.dominio.texto import normalizar

CATEGORIAS = ("externas", "internas", "plantas")


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
        for cat in CATEGORIAS:
            bloco = ult.get(cat)
            if bloco and bloco["qtd"]:
                out[cat] = bloco["total"] / bloco["qtd"]
        return out

    def tabela_precos_inferida(self, nome: str) -> dict[str, dict[str, int]] | None:
        ult = self._ultima(nome)
        if not ult:
            return None
        tabela: dict[str, dict[str, int]] = {cat: {} for cat in CATEGORIAS}
        for cat in CATEGORIAS:
            for it in ult.get(cat, {}).get("itens", []):
                tabela[cat][normalizar(it["desc"])] = it["preco"]
        return tabela
```

Nota: `upsert_cliente` é importado aqui apenas para deixar a dependência explícita do pacote; se o linter reclamar de import não usado, remova-o — os testes usam `upsert_cliente` direto de `repo_propostas`.

- [ ] **Step 4: Implementar `orcamento_historico.py`**

`aut-proposta/app/historico/orcamento_historico.py`:

```python
"""2º levantamento: reaplica os preços que o cliente pagou no último projeto.

Ordem de resolução de preço por item: item exato no histórico → item similar
(substring) → média da categoria do cliente → preço de planilha (fallback).
"""
from __future__ import annotations

from app.dominio.orcamento import (
    CATEGORIAS,
    CategoriaOrcada,
    ItemOrcado,
    Orcamento,
    _formata_descricao,
)
from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar
from app.historico.historico import Historico


def orcar_pelo_historico(
    historico: Historico,
    cliente: str,
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos,
) -> Orcamento | None:
    if not historico.tem_cliente(cliente):
        return None

    tab_cliente = historico.tabela_precos_inferida(cliente) or {}
    medias = historico.medias_por_categoria(cliente) or {}

    cats: dict[str, CategoriaOrcada] = {c: CategoriaOrcada(nome=c) for c in CATEGORIAS}

    for cat in CATEGORIAS:
        for desc in descricoes.get(cat, []):
            chave = normalizar(desc)
            preco: int | None = None
            fonte = ""

            if chave in tab_cliente.get(cat, {}):
                preco = tab_cliente[cat][chave]
                fonte = f"historico:{cliente}:item_exato"

            if preco is None:
                for k_hist, v_hist in tab_cliente.get(cat, {}).items():
                    if chave in k_hist or k_hist in chave:
                        preco = v_hist
                        fonte = f"historico:{cliente}:item_similar"
                        break

            if preco is None and cat in medias:
                preco = int(round(medias[cat]))
                fonte = f"historico:{cliente}:media_categoria"

            if preco is None:
                classif = tabela.classificar(desc, cat)
                preco = classif["preco"]
                fonte = f"fallback_planilha:{classif['chave']}"

            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=_formata_descricao(desc, cat),
                    preco=preco,
                    fonte=fonte,
                )
            )

    return Orcamento(
        estrategia=f"historico:{cliente}",
        externas=cats["externas"],
        internas=cats["internas"],
        plantas=cats["plantas"],
    )
```

- [ ] **Step 5: Rodar e ver passar (suíte inteira)**

Run: `pytest -v`
Expected: PASS — Plano 1 (25) + testes de banco/histórico do Plano 2 (passam com o Docker no ar; pulam sem ele).

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/app/historico/ aut-proposta/tests/historico/
git commit -m "feat(proposta): histórico e 2º levantamento (orçamento por histórico)"
```

---

## Self-Review

**Cobertura do spec (design, Seções 3–5, parte de persistência/histórico):**
- Schema NEON `clientes/propostas/proposta_itens/tabela_precos` (Seção 3) → Tasks 2 (schema), com preços em `preco_categoria`+`preco_item`. ✔
- Seed da tabela de preços a partir da planilha/JSON (Seção 2/3) → Task 3. ✔
- **NEON como única fonte de preços em runtime** → Task 4 (`carregar_tabela_precos`), provado por teste de paridade com o JSON. ✔
- Histórico consultável e 2º levantamento (Seção 2 "2 levantamentos"; Seção 6 passo 3) → Tasks 5 e 6. ✔
- Persistência da proposta final (Seção 6 passo 5, sem o R2 ainda) → Task 5 (`salvar_proposta`; `docx_url` fica nulo até o Plano 3). ✔
- **Fora deste plano (intencional):** docx, R2, IA/OpenAI, API HTTP, UI → Plano 3 e 4.

**Placeholders:** nenhum "TBD"/"handle edge cases"; todo SQL e código presentes.

**Consistência de tipos/nomes:**
- `carregar_tabela_precos` monta o mesmo `dados` que `TabelaPrecos.__init__` espera (`_default`, `_descricao_padrao`, `tabela:[{chave,descricao,preco,padroes}]`) — igual ao formato do JSON do Plano 1. ✔
- `salvar_proposta` consome exatamente a estrutura de `fechar_orcamento` do Plano 1 (`{"orcamento":{...,"externas":{"itens":[{"descricao","preco","fonte"}]}}, "financeiro":{"desconto_pct","desconto_valor","total"}}`). ✔
- `ultima_proposta_estruturada` devolve `{cat:{"qtd","total","itens":[{"desc","preco"}]}}`, consumido por `Historico` e por `orcar_pelo_historico` — mesmos nomes de chave. ✔
- `orcar_pelo_historico` reusa `CATEGORIAS`, `CategoriaOrcada`, `ItemOrcado`, `Orcamento`, `_formata_descricao` do domínio (Plano 1) sem alterá-los; `_formata_descricao` existe em `app/dominio/orcamento.py`. ✔
- `normalizar` (não `_norm`) usado em `repo_propostas`, `historico` e `orcamento_historico`. ✔

**Pureza do domínio:** nenhum arquivo novo em `app/dominio/`; `app/dominio/` permanece sem `psycopg`. Código de banco em `app/db/`; composição em `app/historico/`. ✔

**Dependência de import:** `orcamento_historico` importa `_formata_descricao` de `app.dominio.orcamento` (função de módulo, existe) — sem ciclo, pois o domínio não importa `app/historico`.
