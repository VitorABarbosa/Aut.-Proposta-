# Automação de Proposta — Plano 4: UI no Hub + Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ferramenta "Proposta" utilizável de ponta a ponta: UI no hub `flyingstudio-tools` (texto livre → preview precificado ao vivo → pendências obrigatórias preenchidas → ajustes → .docx e .pdf) e o serviço `aut-proposta` no ar no Railway.

**Architecture:** No hub (Next.js 14 App Router), um novo agente em `src/components/agents/proposta/` no padrão dos existentes (AgentShell + fluxo de painéis), falando com o backend SEMPRE via proxy `src/app/api/tools/proposta/[...route]/route.ts` (sessão Better Auth + `tool_permissions` + header `Authorization: Bearer` injetado server-side — o token nunca chega ao browser). No backend, uma única mudança: `/levantamento` passa a aceitar `estrutura` (para reprecificar edições do preview). Fecha com deploy Railway + smoke test de produção.

**Tech Stack:** Next.js 14.2 (App Router, TS), Tailwind 3.4 (tokens `brand.*`), lucide-react, Jest + Testing Library; FastAPI (aut-proposta) já pronto; Railway (Docker).

## Roadmap dos planos (contexto)

Plano 4 de 4 — final. (1) núcleo ✅ (2) NEON+histórico ✅ (3) docx+IA+API ✅. **(4) UI no hub + deploy (este).**

## Dois repositórios

- **aut-proposta** (este repo, `AUT_PROPOSTA/aut-proposta/`): Task 1. Branch `feat/plano-4-levantamento-estrutura`.
- **hub** (`C:\Users\power\OneDrive\Documentos\PROJETOS_\Trabalhos\FlyingStudio\SITES\FLYINGSTUDIO_OLD\flyingstudio-tools`): Tasks 2-4. Branch `feat/proposta-agent`. Rodar `npm test`/`npm run build` a partir da raiz do hub.

## Global Constraints

- **Hub:** TypeScript; UI text em português; wrapper raiz `AgentShell` (`src/components/tools/AgentShell.tsx`, props `{title, description?, statusBadge?, children}`); classes com `cn()` de `src/lib/cn.ts`; tokens `brand-purple #7E54FE` / `brand-lime #A3E635`; cards `rounded-xl border p-6 bg-[#F1F1F1] dark:bg-[#1A1A1A] border-gray-200 dark:border-gray-700`; ícones lucide-react.
- **Segurança:** browser NUNCA fala com o serviço direto nem vê token. Envs do hub são server-only, SEM prefixo `NEXT_PUBLIC_`: `PROPOSTA_URL`, `PROPOSTA_API_TOKEN` (não precisam de ARG no Dockerfile do hub). O proxy revalida sessão + `hasToolPermission(userId, 'proposta')` em TODA request (o gate da página não protege a API).
- **Backend:** `app/dominio/` intocado; a IA nunca vê/produz preço; NEON única fonte de preços; código do aut-proposta em português.
- Slug da ferramenta: **`proposta`** — idêntico em `src/config/tools.ts` (`id`), `AGENT_COMPONENTS`, rota do proxy e linhas da tabela `tool_permissions`.
- `AreaSlug` é união fechada — usar `areas: ['comercial']`.
- Contratos da API (Plano 3 + este plano): `POST /levantamento` → `{estrutura, fechado, estrategia_usada, avisos, pendencias}`; `POST /propostas` → `{proposta_id, docx_url, download, fechado, avisos}`; `GET /propostas/{id}/docx` → FileResponse; `GET /propostas/{id}/pdf` → FileResponse (novo). `estrutura` = `{cliente:{empresa,ref,contato}, externas[], internas[], plantas[], desconto_pct, desconto_label, estrategia, mostrar_precos_individuais, _avisos[]}`.
- **Requisitos obrigatórios de uma proposta** (decisão do usuário 2026-07-19): construtora/incorporadora (`cliente.empresa`), empreendimento (`cliente.ref`), A/C — responsável que recebe (`cliente.contato`) e ≥1 item/serviço. O backend devolve `pendencias: string[]` no levantamento (vazia quando tudo preenchido — os defaults do parser `"CLIENTE"`, `"PROJETO"` e `"—"` contam como FALTANDO); a UI bloqueia "Gerar" enquanto houver pendência e oferece campos para completar. O `POST /propostas` continua permissivo (a trava é da UI).
- **PDF** (decisão do usuário): propostas são enviadas em PDF. Conversão docx→pdf server-side via LibreOffice headless (`soffice`); no ambiente sem `soffice` o endpoint devolve **501** com mensagem clara (o teste local pula). O Dockerfile instala `libreoffice-writer` + `fonts-crosextra-carlito` (métrica compatível com Calibri).

---

### Task 1: Backend — `/levantamento` aceita `estrutura` + pendências obrigatórias

**Repo:** aut-proposta (branch `feat/plano-4-levantamento-estrutura`).

**Files:**
- Modify: `aut-proposta/app/api/main.py` (CorpoLevantamento + rota + `_pendencias`)
- Test: `aut-proposta/tests/api/test_api.py` (4 testes novos)

**Interfaces:**
- Consumes: `levantar(conn, estrutura)` (já existe).
- Produces:
  - `POST /levantamento` aceita `{"texto": str}` OU `{"estrutura": dict}` (como `POST /propostas` já faz); com `estrutura`, pula o parser e reprecifica direto; resposta inclui a `estrutura` usada. Nenhum dos dois → 422.
  - Resposta ganha `pendencias: string[]` — mensagens dos requisitos faltantes: `cliente.empresa` vazio ou `"CLIENTE"`; `cliente.ref` vazio ou `"PROJETO"`; `cliente.contato` vazio ou `"—"`; `total_imagens == 0`. Vazia quando tudo preenchido.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

Em `aut-proposta/tests/api/test_api.py`, adicionar ao final:

```python
def test_levantamento_por_estrutura_reprecifica(cliente_api):
    estrutura = {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
        "desconto_pct": 5.0, "desconto_label": "ajuste", "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    r = cliente_api.post("/levantamento", json={"estrutura": estrutura}, headers=HEAD)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["estrutura"]["cliente"]["empresa"] == "GALLI"
    assert corpo["fechado"]["orcamento"]["subtotal"] == 3000
    assert corpo["fechado"]["financeiro"]["desconto_pct"] == 5.0


def test_levantamento_sem_texto_nem_estrutura_422(cliente_api):
    r = cliente_api.post("/levantamento", json={}, headers=HEAD)
    assert r.status_code == 422


def test_pendencias_apontam_requisitos_faltantes(cliente_api):
    # Texto sem A/C e sem ref: parser preenche defaults, que contam como faltando.
    r = cliente_api.post("/levantamento", json={"texto": "Externas: Fachada"}, headers=HEAD)
    assert r.status_code == 200
    pend = r.json()["pendencias"]
    assert any("construtora" in p.lower() or "cliente" in p.lower() for p in pend)
    assert any("a/c" in p.lower() or "respons" in p.lower() for p in pend)
    assert any("empreendimento" in p.lower() or "projeto" in p.lower() for p in pend)


def test_pendencias_vazia_quando_completo(cliente_api):
    r = cliente_api.post("/levantamento", json={"texto": TEXTO}, headers=HEAD)
    assert r.status_code == 200
    assert r.json()["pendencias"] == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run (de `aut-proposta/`, com `docker compose up -d db-test`): `pytest tests/api -v`
Expected: FAIL nos 2 novos (validação atual exige `texto`).

- [ ] **Step 3: Implementar**

Em `aut-proposta/app/api/main.py`: substituir `CorpoLevantamento` e a rota:

```python
class CorpoLevantamento(BaseModel):
    texto: str | None = None
    estrutura: dict | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if self.texto is None and self.estrutura is None:
            raise ValueError("Envie 'texto' ou 'estrutura'.")
        return self
```

```python
def _pendencias(estrutura: dict, fechado: dict) -> list[str]:
    """Requisitos obrigatórios de toda proposta; defaults do parser contam como faltando."""
    pend: list[str] = []
    cli = estrutura.get("cliente", {})
    if not cli.get("empresa") or cli["empresa"] == "CLIENTE":
        pend.append("Informe a construtora/incorporadora (cliente).")
    if not cli.get("ref") or cli["ref"] == "PROJETO":
        pend.append("Informe o empreendimento/projeto (ref).")
    if not cli.get("contato") or cli["contato"] == "—":
        pend.append("Informe o A/C — responsável que recebe a proposta.")
    if fechado["orcamento"]["total_imagens"] == 0:
        pend.append("Nenhum item identificado — liste as imagens/serviços contratados.")
    return pend


@app.post("/levantamento", dependencies=[Depends(verificar_token)])
def rota_levantamento(corpo: CorpoLevantamento):
    estrutura = corpo.estrutura if corpo.estrutura is not None else parse(corpo.texto)
    conn = _abrir_conn()
    try:
        lev = levantar(conn, estrutura)
    finally:
        _fechar_conn(conn)
    return {
        "estrutura": estrutura,
        "fechado": lev["fechado"],
        "estrategia_usada": lev["estrategia_usada"],
        "avisos": lev["avisos"],
        "pendencias": _pendencias(estrutura, lev["fechado"]),
    }
```

- [ ] **Step 4: Rodar e ver passar (suíte inteira)**

Run: `pytest -q`
Expected: 85 passed (81 + 4).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/api/main.py aut-proposta/tests/api/test_api.py
git commit -m "feat(proposta): /levantamento aceita estrutura + pendências obrigatórias"
```

---

### Task 1B: Backend — download em PDF (docx → pdf via LibreOffice)

**Repo:** aut-proposta (mesma branch).

**Files:**
- Create: `aut-proposta/app/docx/pdf.py`
- Modify: `aut-proposta/app/api/main.py` (rota `GET /propostas/{id}/pdf`)
- Modify: `aut-proposta/Dockerfile` (instalar LibreOffice)
- Test: `aut-proposta/tests/docx/test_pdf.py`, mais 1 teste em `tests/api/test_api.py`

**Interfaces:**
- Consumes: o `.docx` já gerado em `PROPOSTAS_DIR/proposta_<id>.docx`.
- Produces:
  - `app.docx.pdf.converter_para_pdf(docx: Path) -> Path | None` — converte via `soffice --headless --convert-to pdf` no mesmo diretório; `None` se o LibreOffice não estiver instalado; propaga erro do subprocesso em falha real.
  - `GET /propostas/{id}/pdf` — converte on-demand (cacheia: se o `.pdf` já existe, serve direto); 404 se o `.docx` não existe; **501** se o conversor não está disponível no servidor.

- [ ] **Step 1: Escrever os testes (falha primeiro)**

`aut-proposta/tests/docx/test_pdf.py`:

```python
import shutil

import pytest

from app.docx.pdf import converter_para_pdf

tem_soffice = bool(shutil.which("soffice") or shutil.which("libreoffice"))


@pytest.mark.skipif(not tem_soffice, reason="LibreOffice (soffice) não instalado — validado no Docker")
def test_converte_docx_gerado_para_pdf(tmp_path):
    import datetime as dt
    from app.docx.gerador import gerar_docx

    cliente = {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"}
    fechado = {
        "orcamento": {"estrategia": "planilha", "subtotal": 3000, "total_imagens": 1,
                      "externas": {"nome": "externas", "qtd": 1, "total": 3000,
                                   "itens": [{"descricao": "Perspectiva Fachada", "preco": 3000, "fonte": "planilha"}]},
                      "internas": {"nome": "internas", "qtd": 0, "total": 0, "itens": []},
                      "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []}},
        "financeiro": {"subtotal": 3000, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 3000.0, "rotulo": ""},
    }
    docx = tmp_path / "p.docx"
    gerar_docx(cliente, fechado, docx, data=dt.date(2026, 7, 19))
    pdf = converter_para_pdf(docx)
    assert pdf is not None and pdf.exists()
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_sem_soffice_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nome: None)
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    assert converter_para_pdf(arq) is None
```

Em `aut-proposta/tests/api/test_api.py`, adicionar:

```python
def test_pdf_de_proposta_inexistente_404(cliente_api):
    r = cliente_api.get("/propostas/99999/pdf", headers=HEAD)
    assert r.status_code == 404
```

Run: `pytest tests/docx/test_pdf.py tests/api -v` → FAIL (ModuleNotFoundError: app.docx.pdf).

- [ ] **Step 2: Implementar**

`aut-proposta/app/docx/pdf.py`:

```python
"""Conversão docx -> pdf via LibreOffice headless (instalado no Docker)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def converter_para_pdf(docx: Path) -> Path | None:
    """Converte no mesmo diretório. None se o LibreOffice não está instalado."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", str(docx.parent), str(docx)],
        check=True, capture_output=True, timeout=120,
    )
    pdf = docx.with_suffix(".pdf")
    return pdf if pdf.exists() else None
```

Em `aut-proposta/app/api/main.py`, importar `from app.docx.pdf import converter_para_pdf` e adicionar a rota:

```python
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
```

No `aut-proposta/Dockerfile`, logo após o `FROM`:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Rodar e ver passar**

Run: `pytest -q`
Expected: tudo verde; `test_converte_docx_gerado_para_pdf` PULA se o LibreOffice não estiver instalado localmente (será validado no build Docker da Task 5).

- [ ] **Step 4: Commit**

```bash
git add aut-proposta/app/docx/pdf.py aut-proposta/app/api/main.py aut-proposta/Dockerfile aut-proposta/tests/docx/test_pdf.py aut-proposta/tests/api/test_api.py
git commit -m "feat(proposta): download em PDF (conversão LibreOffice on-demand)"
```

---

### Task 2: Hub — proxy autenticado + registro da ferramenta

**Repo:** hub (branch `feat/proposta-agent` a partir da branch principal do hub).

**Files:**
- Create: `src/app/api/tools/proposta/[...route]/route.ts`
- Modify: `src/config/tools.ts` (entrada nova no array `tools`)
- Modify: `src/app/tools/[slug]/page.tsx` (import + linha em `AGENT_COMPONENTS` — com um componente stub até a Task 4)
- Create: `src/components/agents/proposta/PropostaAgent.tsx` (stub mínimo desta task, substituído na Task 4)
- Modify: `.env.example` (duas envs novas)
- Modify: `db/tool_permissions.sql` OU registrar via painel admin (ver Step 5)

**Interfaces:**
- Consumes: `auth` (`@/lib/auth`), `hasToolPermission` (`@/lib/permissions`), envs `PROPOSTA_URL`, `PROPOSTA_API_TOKEN`.
- Produces: qualquer chamada `/api/tools/proposta/<path>` → sessão + permissão validadas → repassada a `${PROPOSTA_URL}/<path>` com `Authorization: Bearer ${PROPOSTA_API_TOKEN}`; binários (docx) repassados com content-type/disposition. Ferramenta "Proposta" visível na área Comercial.

**Nota:** o modelo é `src/app/api/tools/lumen/[...route]/route.ts` — ANTES de escrever, leia-o e mantenha a mesma estrutura/assinaturas do projeto (se algo abaixo divergir do LUMEN real, o LUMEN governa), acrescentando apenas o header Authorization e o 503 sem envs.

- [ ] **Step 1: Criar o proxy**

`src/app/api/tools/proposta/[...route]/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@/lib/auth'
import { hasToolPermission } from '@/lib/permissions'

// Proxy autenticado para o serviço aut-proposta (FastAPI).
// O gate visual em tools/[slug]/page.tsx NÃO protege a API — este handler
// revalida sessão + permissão em toda request e injeta o token server-side.
const BASE = process.env.PROPOSTA_URL ?? ''
const TOKEN = process.env.PROPOSTA_API_TOKEN ?? ''

const BINARIOS = ['application/vnd.openxmlformats', 'application/octet-stream', 'application/zip']

async function handler(req: NextRequest, { params }: { params: { route: string[] } }) {
  const session = await auth.api.getSession({ headers: req.headers })
  if (!session) {
    return NextResponse.json({ error: 'Não autenticado' }, { status: 401 })
  }
  const permitido = await hasToolPermission(session.user.id, 'proposta')
  if (!permitido) {
    return NextResponse.json({ error: 'Sem permissão para esta ferramenta' }, { status: 403 })
  }
  if (!BASE || !TOKEN) {
    return NextResponse.json({ error: 'PROPOSTA_URL/PROPOSTA_API_TOKEN não configurados' }, { status: 503 })
  }

  const path = params.route.join('/')
  const url = `${BASE.replace(/\/$/, '')}/${path}${req.nextUrl.search}`
  const headers: Record<string, string> = { Authorization: `Bearer ${TOKEN}` }
  const contentType = req.headers.get('content-type')
  if (contentType) headers['content-type'] = contentType

  const resp = await fetch(url, {
    method: req.method,
    headers,
    body: req.method === 'GET' || req.method === 'HEAD' ? undefined : await req.arrayBuffer(),
  })

  const respType = resp.headers.get('content-type') ?? 'application/json'
  const respHeaders: Record<string, string> = { 'content-type': respType }
  const disposition = resp.headers.get('content-disposition')
  if (disposition) respHeaders['content-disposition'] = disposition

  if (BINARIOS.some((b) => respType.startsWith(b))) {
    return new NextResponse(await resp.arrayBuffer(), { status: resp.status, headers: respHeaders })
  }
  return new NextResponse(await resp.text(), { status: resp.status, headers: respHeaders })
}

export { handler as GET, handler as POST, handler as PUT, handler as DELETE, handler as PATCH }
```

- [ ] **Step 2: Stub do agente**

`src/components/agents/proposta/PropostaAgent.tsx` (mínimo para a rota compilar; substituído na Task 4):

```tsx
'use client'

import { AgentShell } from '@/components/tools/AgentShell'

export function PropostaAgent() {
  return (
    <AgentShell
      title="Proposta"
      description="Gere propostas comerciais em .docx a partir de uma descrição livre."
    >
      <p className="text-gray-500 dark:text-gray-400">Em construção…</p>
    </AgentShell>
  )
}
```

- [ ] **Step 3: Registrar a ferramenta**

Em `src/config/tools.ts`, adicionar ao array `tools` (seguindo o shape exato das entradas existentes — confira os campos reais do tipo `Tool`):

```ts
{
  id: 'proposta',
  name: 'Proposta',
  description: 'Propostas comerciais em .docx: descreva o pedido, revise o preço e gere o documento.',
  status: 'active',
  href: '/tools/proposta',
  icon: 'FileText',
  areas: ['comercial'],
  requiresAuth: true,
},
```

Em `src/app/tools/[slug]/page.tsx`:

```ts
import { PropostaAgent } from '@/components/agents/proposta/PropostaAgent'
// ...
const AGENT_COMPONENTS: Record<string, React.ComponentType> = {
  // ...existentes,
  proposta: PropostaAgent,
}
```

- [ ] **Step 4: Envs**

Em `.env.example`, adicionar:

```bash
# Serviço aut-proposta (server-only — o proxy injeta o token; nunca NEXT_PUBLIC_)
PROPOSTA_URL="http://localhost:8000"
PROPOSTA_API_TOKEN="mesmo-API_TOKEN-do-servico"
```

No `.env.local` real do hub, preencher com o token do `aut-proposta/.env` local.

- [ ] **Step 5: Permissão**

Conceder o slug `proposta` ao seu usuário: preferir o painel admin (`/admin`) se ele permitir atribuir ferramenta; senão, inserir na tabela `tool_permissions` seguindo o shape de `db/tool_permissions.sql` (conferir colunas reais antes do INSERT).

- [ ] **Step 6: Verificar build e smoke local**

Run (raiz do hub): `npm run build`
Expected: build OK sem erros de tipo.

Smoke (com o serviço local no ar: `uvicorn app.api.main:app` em `aut-proposta/`, e `npm run dev` no hub): logado no hub, abrir `/tools/proposta` → stub aparece; `POST /api/tools/proposta/levantamento` via UI da Task 4 (ou aguardar Task 4 — nesta task basta a página abrir e o card aparecer na área Comercial).

- [ ] **Step 7: Commit (no repo do hub)**

```bash
git checkout -b feat/proposta-agent
git add src/app/api/tools/proposta/ src/components/agents/proposta/ src/config/tools.ts "src/app/tools/[slug]/page.tsx" .env.example
git commit -m "feat(proposta): proxy autenticado e registro da ferramenta no hub"
```

---

### Task 3: Hub — tipos e hook de API

**Repo:** hub (mesma branch).

**Files:**
- Create: `src/components/agents/proposta/types.ts`
- Create: `src/components/agents/proposta/useProposta.ts`
- Test: `src/components/agents/proposta/__tests__/useProposta.test.ts`

**Interfaces:**
- Consumes: proxy `/api/tools/proposta/*` (Task 2).
- Produces:
  - Tipos `Estrutura`, `Fechado`, `Levantamento`, `PropostaGerada`, `CategoriaKey` (usados pela Task 4).
  - `useProposta()` → `{ carregando, erro, levantamento, gerada, levantarPorTexto(texto), reprecificar(estrutura), gerar(estrutura), reiniciar() }`.

- [ ] **Step 1: Tipos**

`src/components/agents/proposta/types.ts`:

```ts
export type CategoriaKey = 'externas' | 'internas' | 'plantas'

export interface Cliente {
  empresa: string
  ref: string
  contato: string
}

export interface Estrutura {
  cliente: Cliente
  externas: string[]
  internas: string[]
  plantas: string[]
  desconto_pct: number
  desconto_label: string | null
  estrategia: 'auto' | 'planilha' | 'historico'
  mostrar_precos_individuais: boolean
  _avisos: string[]
}

export interface ItemOrcado {
  descricao: string
  preco: number
  fonte: string
}

export interface CategoriaOrcada {
  nome: string
  qtd: number
  total: number
  itens: ItemOrcado[]
}

export interface Fechado {
  orcamento: {
    estrategia: string
    subtotal: number
    total_imagens: number
    externas: CategoriaOrcada
    internas: CategoriaOrcada
    plantas: CategoriaOrcada
  }
  financeiro: {
    subtotal: number
    desconto_pct: number
    desconto_valor: number
    total: number
    rotulo: string
  }
}

export interface Levantamento {
  estrutura: Estrutura
  fechado: Fechado
  estrategia_usada: string
  avisos: string[]
  pendencias: string[]
}

export interface PropostaGerada {
  proposta_id: number
  docx_url: string | null
  download: string
  fechado: Fechado
  avisos: string[]
}
```

- [ ] **Step 2: Teste do hook (falha primeiro)**

`src/components/agents/proposta/__tests__/useProposta.test.ts`:

```ts
import { act, renderHook } from '@testing-library/react'
import { useProposta } from '../useProposta'

const LEVANTAMENTO = {
  estrutura: { cliente: { empresa: 'GALLI', ref: 'Aurora', contato: '—' } },
  fechado: { financeiro: { total: 3000 } },
  estrategia_usada: 'planilha',
  avisos: [],
  pendencias: [],
}

describe('useProposta', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })

  it('levantarPorTexto popula levantamento', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => LEVANTAMENTO,
    })
    const { result } = renderHook(() => useProposta())
    await act(() => result.current.levantarPorTexto('cliente GALLI'))
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/tools/proposta/levantamento',
      expect.objectContaining({ method: 'POST' })
    )
    expect(result.current.levantamento?.estrategia_usada).toBe('planilha')
    expect(result.current.erro).toBeNull()
  })

  it('erro HTTP vira mensagem e não quebra', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 503,
      text: async () => 'sem token',
    })
    const { result } = renderHook(() => useProposta())
    await act(() => result.current.levantarPorTexto('x'))
    expect(result.current.erro).toContain('503')
    expect(result.current.levantamento).toBeNull()
  })

  it('gerar popula gerada e reiniciar limpa tudo', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ proposta_id: 7, download: '/propostas/7/docx', docx_url: null, avisos: [] }),
    })
    const { result } = renderHook(() => useProposta())
    await act(() => result.current.gerar({} as never))
    expect(result.current.gerada?.proposta_id).toBe(7)
    act(() => result.current.reiniciar())
    expect(result.current.gerada).toBeNull()
  })
})
```

Run: `npx jest src/components/agents/proposta --silent`
Expected: FAIL (useProposta não existe).

- [ ] **Step 3: Implementar o hook**

`src/components/agents/proposta/useProposta.ts`:

```ts
'use client'

import { useCallback, useState } from 'react'
import type { Estrutura, Levantamento, PropostaGerada } from './types'

const BASE = '/api/tools/proposta'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const detalhe = await resp.text()
    throw new Error(`Erro ${resp.status}: ${detalhe.slice(0, 300)}`)
  }
  return resp.json() as Promise<T>
}

export function useProposta() {
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [levantamento, setLevantamento] = useState<Levantamento | null>(null)
  const [gerada, setGerada] = useState<PropostaGerada | null>(null)

  const executar = useCallback(async (fn: () => Promise<void>) => {
    setCarregando(true)
    setErro(null)
    try {
      await fn()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro inesperado')
    } finally {
      setCarregando(false)
    }
  }, [])

  const levantarPorTexto = useCallback(
    (texto: string) =>
      executar(async () => {
        setLevantamento(await postJson<Levantamento>('/levantamento', { texto }))
      }),
    [executar]
  )

  const reprecificar = useCallback(
    (estrutura: Estrutura) =>
      executar(async () => {
        setLevantamento(await postJson<Levantamento>('/levantamento', { estrutura }))
      }),
    [executar]
  )

  const gerar = useCallback(
    (estrutura: Estrutura) =>
      executar(async () => {
        setGerada(await postJson<PropostaGerada>('/propostas', { estrutura }))
      }),
    [executar]
  )

  const reiniciar = useCallback(() => {
    setLevantamento(null)
    setGerada(null)
    setErro(null)
  }, [])

  return { carregando, erro, levantamento, gerada, levantarPorTexto, reprecificar, gerar, reiniciar }
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npx jest src/components/agents/proposta --silent`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/components/agents/proposta/
git commit -m "feat(proposta): tipos e hook de API do agente"
```

---

### Task 4: Hub — UI do agente (entrada + preview + resultado)

**Repo:** hub (mesma branch).

**Files:**
- Modify: `src/components/agents/proposta/PropostaAgent.tsx` (substitui o stub)
- Create: `src/components/agents/proposta/EntradaPainel.tsx`
- Create: `src/components/agents/proposta/PreviewPainel.tsx`
- Create: `src/components/agents/proposta/ResultadoPainel.tsx`
- Test: `src/components/agents/proposta/__tests__/PreviewPainel.test.tsx`

**Interfaces:**
- Consumes: `useProposta` + tipos (Task 3), `AgentShell`, `cn()`, lucide-react.
- Produces: fluxo completo — descrever → "Precificar" → tela dividida (estrutura editável à esquerda, preview financeiro à direita) → "Gerar .docx" → resultado com download (via proxy `/api/tools/proposta/propostas/{id}/docx`) e link R2 quando houver.
- Edições suportadas (o que o backend reprecifica): remover item de categoria, adicionar item (texto curto), mudar `desconto_pct`/`desconto_label`, trocar `estrategia`, e **editar os dados do cliente** (empresa/ref/contato — campos sempre visíveis no topo do preview). Toda edição chama `reprecificar(estruturaEditada)`.
- **Pendências**: `levantamento.pendencias` aparece como lista destacada (âmbar) no preview; o botão "Gerar" fica desabilitado enquanto `pendencias.length > 0`, com legenda "Complete as pendências para gerar".
- **PDF**: `ResultadoPainel` ganha o botão "Baixar PDF" → `/api/tools/proposta/propostas/{id}/pdf` (ao lado do .docx). Se o backend responder 501, o navegador mostra o erro do proxy — aceitável nesta versão.

- [ ] **Step 1: Teste do PreviewPainel (falha primeiro)**

`src/components/agents/proposta/__tests__/PreviewPainel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { PreviewPainel } from '../PreviewPainel'
import type { Levantamento } from '../types'

const LEV: Levantamento = {
  estrutura: {
    cliente: { empresa: 'GALLI', ref: 'Aurora', contato: 'Daniel' },
    externas: ['Fachada'],
    internas: [],
    plantas: [],
    desconto_pct: 10,
    desconto_label: 'parceria',
    estrategia: 'planilha',
    mostrar_precos_individuais: false,
    _avisos: [],
  },
  fechado: {
    orcamento: {
      estrategia: 'planilha',
      subtotal: 3000,
      total_imagens: 1,
      externas: {
        nome: 'externas', qtd: 1, total: 3000,
        itens: [{ descricao: 'Perspectiva Fachada', preco: 3000, fonte: 'planilha:fachada' }],
      },
      internas: { nome: 'internas', qtd: 0, total: 0, itens: [] },
      plantas: { nome: 'plantas', qtd: 0, total: 0, itens: [] },
    },
    financeiro: { subtotal: 3000, desconto_pct: 10, desconto_valor: 300, total: 2700, rotulo: 'parceria' },
  },
  estrategia_usada: 'planilha',
  avisos: ['aviso de teste'],
  pendencias: [],
}

describe('PreviewPainel', () => {
  it('mostra pendências destacadas quando existem', () => {
    const comPendencia = { ...LEV, pendencias: ['Informe o A/C — responsável que recebe a proposta.'] }
    render(<PreviewPainel levantamento={comPendencia} onEditar={jest.fn()} carregando={false} />)
    expect(screen.getByText(/Informe o A\/C/)).toBeInTheDocument()
  })

  it('editar empresa do cliente devolve estrutura atualizada', () => {
    const onEditar = jest.fn()
    render(<PreviewPainel levantamento={LEV} onEditar={onEditar} carregando={false} />)
    const campo = screen.getByLabelText('Cliente')
    fireEvent.change(campo, { target: { value: 'BRNPAR' } })
    fireEvent.blur(campo)
    expect(onEditar).toHaveBeenCalledWith(
      expect.objectContaining({ cliente: expect.objectContaining({ empresa: 'BRNPAR' }) })
    )
  })

  it('mostra itens, totais e avisos', () => {
    render(<PreviewPainel levantamento={LEV} onEditar={jest.fn()} carregando={false} />)
    expect(screen.getByText('Perspectiva Fachada')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s?3\.000,00/)).toBeInTheDocument()
    expect(screen.getByText(/R\$\s?2\.700,00/)).toBeInTheDocument()
    expect(screen.getByText('aviso de teste')).toBeInTheDocument()
  })

  it('remover item devolve estrutura sem ele', () => {
    const onEditar = jest.fn()
    render(<PreviewPainel levantamento={LEV} onEditar={onEditar} carregando={false} />)
    fireEvent.click(screen.getByLabelText('Remover Fachada'))
    expect(onEditar).toHaveBeenCalledWith(
      expect.objectContaining({ externas: [] })
    )
  })
})
```

Run: `npx jest src/components/agents/proposta --silent` → FAIL (PreviewPainel não existe).

- [ ] **Step 2: Implementar os componentes**

`src/components/agents/proposta/EntradaPainel.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/cn'

const EXEMPLO = `Cliente: GALLI, ref Residencial Aurora, a/c Daniel
Externas: Fachada vista da calçada, Jardim
Internas: Academia, Lobby
Plantas: Implantação Térreo, Apartamento Tipo
10% de desconto, preço de planilha`

interface Props {
  onPrecificar: (texto: string) => void
  carregando: boolean
}

export function EntradaPainel({ onPrecificar, carregando }: Props) {
  const [texto, setTexto] = useState('')
  return (
    <div className="rounded-xl border border-gray-200 bg-[#F1F1F1] p-6 dark:border-gray-700 dark:bg-[#1A1A1A]">
      <label className="mb-2 block text-sm font-medium text-[#1A1A2E] dark:text-white">
        Descreva a proposta
      </label>
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={EXEMPLO}
        rows={10}
        className={cn(
          'w-full resize-y rounded-lg border border-gray-200 bg-white p-3 text-sm',
          'text-[#1A1A2E] placeholder:text-gray-400 focus:border-brand-purple focus:outline-none',
          'dark:border-gray-700 dark:bg-[#0F0F0F] dark:text-white'
        )}
      />
      <button
        onClick={() => onPrecificar(texto)}
        disabled={carregando || !texto.trim()}
        className={cn(
          'mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-purple px-4 py-2',
          'text-sm font-semibold text-white transition hover:opacity-90',
          'disabled:cursor-not-allowed disabled:opacity-50'
        )}
      >
        <Sparkles className="h-4 w-4" />
        {carregando ? 'Precificando…' : 'Precificar'}
      </button>
    </div>
  )
}
```

`src/components/agents/proposta/PreviewPainel.tsx`:

```tsx
'use client'

import { useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { CategoriaKey, Estrutura, Levantamento } from './types'

const brl = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const ROTULOS: Record<CategoriaKey, string> = {
  externas: 'Ilustrações Externas',
  internas: 'Ilustrações Internas',
  plantas: 'Plantas Humanizadas',
}

interface Props {
  levantamento: Levantamento
  onEditar: (estrutura: Estrutura) => void
  carregando: boolean
}

export function PreviewPainel({ levantamento, onEditar, carregando }: Props) {
  const { estrutura, fechado, estrategia_usada, avisos, pendencias } = levantamento
  const [novoItem, setNovoItem] = useState<Record<CategoriaKey, string>>({
    externas: '', internas: '', plantas: '',
  })
  // Rascunho local dos campos do cliente; commit no blur/Enter para não
  // reprecificar a cada tecla. Ressincroniza quando o backend responde.
  const [cliente, setCliente] = useState(estrutura.cliente)
  useEffect(() => {
    setCliente(estrutura.cliente)
  }, [estrutura.cliente])

  const commitCliente = () => {
    if (
      cliente.empresa !== estrutura.cliente.empresa ||
      cliente.ref !== estrutura.cliente.ref ||
      cliente.contato !== estrutura.cliente.contato
    ) {
      onEditar({ ...estrutura, cliente })
    }
  }

  const CAMPOS_CLIENTE = [
    { chave: 'empresa', rotulo: 'Cliente', placeholder: 'construtora/incorporadora' },
    { chave: 'ref', rotulo: 'Empreendimento', placeholder: 'nome do projeto' },
    { chave: 'contato', rotulo: 'A/C', placeholder: 'quem recebe a proposta' },
  ] as const

  const remover = (cat: CategoriaKey, idx: number) =>
    onEditar({ ...estrutura, [cat]: estrutura[cat].filter((_, i) => i !== idx) })

  const adicionar = (cat: CategoriaKey) => {
    const desc = novoItem[cat].trim()
    if (!desc) return
    setNovoItem((s) => ({ ...s, [cat]: '' }))
    onEditar({ ...estrutura, [cat]: [...estrutura[cat], desc] })
  }

  const mudarDesconto = (pct: number) =>
    onEditar({ ...estrutura, desconto_pct: Number.isFinite(pct) ? pct : 0 })

  return (
    <div
      className={cn(
        'rounded-xl border border-gray-200 bg-[#F1F1F1] p-6 dark:border-gray-700 dark:bg-[#1A1A1A]',
        carregando && 'pointer-events-none opacity-60'
      )}
    >
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        {CAMPOS_CLIENTE.map(({ chave, rotulo, placeholder }) => (
          <label key={chave} className="block">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{rotulo}</span>
            <input
              aria-label={rotulo}
              value={cliente[chave]}
              placeholder={placeholder}
              onChange={(e) => setCliente((c) => ({ ...c, [chave]: e.target.value }))}
              onBlur={commitCliente}
              onKeyDown={(e) => e.key === 'Enter' && commitCliente()}
              className="mt-0.5 w-full rounded border border-gray-200 bg-white px-2 py-1 text-sm text-[#1A1A2E] dark:border-gray-700 dark:bg-[#0F0F0F] dark:text-white"
            />
          </label>
        ))}
      </div>
      <p className="mb-3 text-xs text-gray-400">estratégia: {estrategia_usada}</p>

      {pendencias.length > 0 && (
        <ul className="mb-4 space-y-1 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-950">
          {pendencias.map((p, i) => (
            <li key={i} className="text-xs font-medium text-amber-700 dark:text-amber-300">
              {p}
            </li>
          ))}
        </ul>
      )}

      {(Object.keys(ROTULOS) as CategoriaKey[]).map((cat) => {
        const bloco = fechado.orcamento[cat]
        return (
          <div key={cat} className="mb-4">
            <p className="mb-1 text-xs font-semibold uppercase text-brand-purple">
              {ROTULOS[cat]}
            </p>
            {bloco.itens.length === 0 && (
              <p className="text-xs text-gray-400">nenhum item</p>
            )}
            <ul>
              {bloco.itens.map((item, idx) => (
                <li
                  key={`${item.descricao}-${idx}`}
                  className="flex items-center justify-between border-b border-gray-200 py-1 text-sm dark:border-gray-700"
                >
                  <span className="text-[#1A1A2E] dark:text-white">{item.descricao}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-medium text-[#1A1A2E] dark:text-white">
                      {brl(item.preco)}
                    </span>
                    <button
                      aria-label={`Remover ${estrutura[cat][idx]}`}
                      onClick={() => remover(cat, idx)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-1 flex gap-2">
              <input
                value={novoItem[cat]}
                onChange={(e) => setNovoItem((s) => ({ ...s, [cat]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && adicionar(cat)}
                placeholder="adicionar item…"
                className="w-full rounded border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-700 dark:bg-[#0F0F0F] dark:text-white"
              />
              <button
                aria-label={`Adicionar em ${ROTULOS[cat]}`}
                onClick={() => adicionar(cat)}
                className="text-brand-purple hover:opacity-70"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
          </div>
        )
      })}

      <div className="mt-4 border-t border-gray-300 pt-3 text-sm dark:border-gray-600">
        <div className="flex justify-between text-gray-500 dark:text-gray-400">
          <span>Subtotal ({fechado.orcamento.total_imagens} imagens)</span>
          <span>{brl(fechado.financeiro.subtotal)}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-2">
            Desconto
            <input
              type="number"
              min={0}
              max={100}
              value={estrutura.desconto_pct}
              onChange={(e) => mudarDesconto(parseFloat(e.target.value))}
              className="w-16 rounded border border-gray-200 bg-white px-1 py-0.5 text-xs dark:border-gray-700 dark:bg-[#0F0F0F] dark:text-white"
            />
            %
          </span>
          <span>-{brl(fechado.financeiro.desconto_valor)}</span>
        </div>
        <div className="mt-2 flex justify-between text-base font-bold text-[#1A1A2E] dark:text-white">
          <span>Investimento</span>
          <span className="text-brand-purple">{brl(fechado.financeiro.total)}</span>
        </div>
      </div>

      {avisos.length > 0 && (
        <ul className="mt-3 space-y-1">
          {avisos.map((a, i) => (
            <li key={i} className="text-xs text-amber-600 dark:text-amber-400">
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

`src/components/agents/proposta/ResultadoPainel.tsx`:

```tsx
'use client'

import { CheckCircle2, Download, ExternalLink, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { PropostaGerada } from './types'

interface Props {
  gerada: PropostaGerada
  onNova: () => void
}

export function ResultadoPainel({ gerada, onNova }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 bg-[#F1F1F1] p-6 text-center dark:border-gray-700 dark:bg-[#1A1A1A]">
      <CheckCircle2 className="mx-auto h-10 w-10 text-brand-lime" />
      <p className="mt-2 font-semibold text-[#1A1A2E] dark:text-white">
        Proposta #{gerada.proposta_id} gerada
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
        <a
          href={`/api/tools/proposta/propostas/${gerada.proposta_id}/pdf`}
          className={cn(
            'inline-flex items-center gap-2 rounded-lg bg-brand-purple px-4 py-2',
            'text-sm font-semibold text-white hover:opacity-90'
          )}
        >
          <Download className="h-4 w-4" /> Baixar PDF
        </a>
        <a
          href={`/api/tools/proposta${gerada.download}`}
          className={cn(
            'inline-flex items-center gap-2 rounded-lg border border-brand-purple px-4 py-2',
            'text-sm font-semibold text-brand-purple hover:bg-brand-purple/10'
          )}
        >
          <Download className="h-4 w-4" /> Baixar .docx
        </a>
        {gerada.docx_url && (
          <a
            href={gerada.docx_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-brand-purple hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Ver no R2
          </a>
        )}
        <button
          onClick={onNova}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-brand-purple dark:text-gray-400"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Nova proposta
        </button>
      </div>
      {gerada.avisos.length > 0 && (
        <ul className="mt-4 space-y-1">
          {gerada.avisos.map((a, i) => (
            <li key={i} className="text-xs text-amber-600 dark:text-amber-400">
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

`src/components/agents/proposta/PropostaAgent.tsx` (substitui o stub):

```tsx
'use client'

import { FileText } from 'lucide-react'
import { AgentShell } from '@/components/tools/AgentShell'
import { cn } from '@/lib/cn'
import { EntradaPainel } from './EntradaPainel'
import { PreviewPainel } from './PreviewPainel'
import { ResultadoPainel } from './ResultadoPainel'
import { useProposta } from './useProposta'

export function PropostaAgent() {
  const {
    carregando, erro, levantamento, gerada,
    levantarPorTexto, reprecificar, gerar, reiniciar,
  } = useProposta()

  return (
    <AgentShell
      title="Proposta"
      description="Descreva o pedido em texto livre; o preço vem da tabela oficial ou do histórico do cliente. Revise, ajuste e gere o .docx timbrado."
    >
      {erro && (
        <p className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300">
          {erro}
        </p>
      )}

      {gerada ? (
        <ResultadoPainel gerada={gerada} onNova={reiniciar} />
      ) : (
        <div className={cn('grid gap-6', levantamento && 'lg:grid-cols-2')}>
          <EntradaPainel onPrecificar={levantarPorTexto} carregando={carregando} />
          {levantamento && (
            <div>
              <PreviewPainel
                levantamento={levantamento}
                onEditar={reprecificar}
                carregando={carregando}
              />
              <button
                onClick={() => gerar(levantamento.estrutura)}
                disabled={carregando || levantamento.pendencias.length > 0}
                className={cn(
                  'mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg',
                  'bg-brand-purple px-4 py-2.5 text-sm font-semibold text-white',
                  'hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50'
                )}
              >
                <FileText className="h-4 w-4" />
                {carregando ? 'Gerando…' : 'Gerar proposta'}
              </button>
              {levantamento.pendencias.length > 0 && (
                <p className="mt-1 text-center text-xs text-amber-600 dark:text-amber-400">
                  Complete as pendências para gerar.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </AgentShell>
  )
}
```

- [ ] **Step 3: Rodar testes e ver passar**

Run: `npx jest src/components/agents/proposta --silent`
Expected: 7 passed (3 do hook + 4 do preview).

- [ ] **Step 4: Verificação manual local (obrigatória)**

Com `uvicorn app.api.main:app` rodando em `aut-proposta/` (com `.env` carregado no ambiente) e `npm run dev` no hub: abrir `/tools/proposta`, colar um texto SEM o A/C → Precificar → pendência âmbar aparece e "Gerar" fica desabilitado; preencher o A/C no campo → pendência some e o botão habilita; remover um item → total recalcula; mudar desconto → recalcula; Gerar → baixar o .docx E o PDF (PDF exige LibreOffice local — sem ele, esperar o erro 501 e validar o PDF na Task 5 em produção). Registrar o resultado no relatório.

- [ ] **Step 5: Build e commit**

Run: `npm run build` → OK.

```bash
git add src/components/agents/proposta/
git commit -m "feat(proposta): UI completa do agente (entrada, preview editável, resultado)"
```

---

### Task 5: Deploy Railway + produção de ponta a ponta

**Repo:** nenhum código novo — configuração e verificação. (Ajustes de env do hub, se necessários, commitados na mesma branch do hub.)

**Interfaces:**
- Consumes: Dockerfile do aut-proposta (Plano 3), envs do `.env` local, painel Railway.
- Produces: serviço público `https://<app>.up.railway.app` com `/saude` OK; hub (local e/ou deploy) apontando para ele.

- [ ] **Step 1: Criar o serviço no Railway**

No painel Railway: New Project → Deploy from GitHub repo → `VitorABarbosa/Aut.-Proposta-`. Em Settings → Root Directory: `aut-proposta` (o Dockerfile está lá). Railway detecta o Dockerfile e usa a porta 8000 (Settings → Networking → Generate Domain, porta 8000).

- [ ] **Step 2: Variáveis de ambiente no Railway**

Copiar do `aut-proposta/.env` local (Variables → Raw Editor):

```
DATABASE_URL=<NEON, o mesmo do .env>
API_TOKEN=<o mesmo do .env>
OPENAI_API_KEY=<quando tiver — sem ela o parser regex assume>
OPENAI_MODEL=gpt-4o-mini
R2_ACCOUNT_ID=<...>
R2_ACCESS_KEY_ID=<...>
R2_SECRET_ACCESS_KEY=<...>
R2_BUCKET=aut-proposta
PROPOSTAS_DIR=saidas
```

- [ ] **Step 3: Smoke test de produção**

```bash
curl https://<dominio-railway>/saude
# esperado: {"ok":true}

curl -s -X POST https://<dominio-railway>/levantamento \
  -H "Authorization: Bearer $API_TOKEN" -H "content-type: application/json" \
  -d '{"texto": "Cliente: SMOKE TEST, ref Piloto\nExternas: Fachada"}'
# esperado: JSON com fechado.orcamento.externas.itens[0].preco = 3000
# e pendencias contendo o aviso de A/C faltando
```

Validar o PDF em produção (o Docker tem LibreOffice): gerar uma proposta de teste via `POST /propostas` e baixar `GET /propostas/{id}/pdf` → arquivo começa com `%PDF-`. Remover a proposta de teste do NEON/R2 ao final.

- [ ] **Step 4: Apontar o hub para produção**

No `.env.local` do hub (e nas variáveis do deploy do hub, se houver): `PROPOSTA_URL=https://<dominio-railway>` e `PROPOSTA_API_TOKEN=<API_TOKEN>`. Repetir a verificação manual da Task 4 Step 4 agora contra produção: precificar → gerar → baixar o .docx → conferir `docx_url` do R2 e a linha em `propostas` no NEON. Remover do NEON/R2 a proposta de teste ao final.

- [ ] **Step 5: Encerrar**

Hub: push da branch `feat/proposta-agent` + PR. aut-proposta: push da branch `feat/plano-4-levantamento-estrutura` + PR. Registrar no ledger o domínio Railway.

---

## Self-Review

**Cobertura do spec (design §3 UI, §6 fluxo, §2 decisões):**
- UI no hub em `src/components/agents/proposta/` (§2/§3) → Tasks 2-4, no padrão AgentShell dos agentes existentes. ✔
- Chat + preview ao vivo → adaptado (decisão do usuário 2026-07-19): texto livre + preview editável reprecificado pelo backend; chat guiado fica como evolução futura. ✔
- Preview mostra tudo antes de gerar (§5) → PreviewPainel (itens, subtotal, desconto editável, total, avisos). ✔
- Controles de desconto recalculam por código (§6 passo 4) → edição chama `/levantamento` com `estrutura` (Task 1); nenhum cálculo no front além de exibição. ✔
- Download do .docx no hub (§6 passo 5) → ResultadoPainel via proxy binário. ✔
- **PDF** (decisão do usuário 2026-07-19; §9 revogado) → Task 1B (`converter_para_pdf` + `GET /propostas/{id}/pdf` + LibreOffice no Docker) + botão "Baixar PDF" no ResultadoPainel; teste local pula sem soffice e a produção é validada na Task 5. ✔
- **Requisitos sempre preenchidos** (decisão do usuário) → `pendencias` no `/levantamento` (Task 1), campos de cliente editáveis no PreviewPainel e trava do "Gerar" no PropostaAgent (Task 4). ✔
- **Nenhuma lógica no hub** (decisão do usuário) → hub só UI + proxy; pendências, preços, IA e PDF são todos calculados no serviço; o front apenas exibe e repassa. ✔
- Auth pelo hub (§3) → proxy com sessão + `tool_permissions` + Bearer server-side. ✔
- Deploy Railway padrão LUMEN (§2) → Task 5. ✔

**Placeholders:** nenhum TBD; todo código presente. Task 5 é operacional (painel Railway) com comandos de verificação concretos.

**Consistência de tipos/nomes:**
- `types.ts` espelha exatamente o JSON da API do Plano 3 (chaves `proposta_id`, `docx_url`, `download`, `fechado.orcamento.<cat>.itens[].{descricao,preco,fonte}`, `financeiro.{subtotal,desconto_pct,desconto_valor,total,rotulo}`). ✔
- `useProposta` retorna `{carregando, erro, levantamento, gerada, levantarPorTexto, reprecificar, gerar, reiniciar}` — mesmos nomes consumidos em `PropostaAgent`. ✔
- `PreviewPainel` props `{levantamento, onEditar, carregando}` idênticas no teste e no uso. ✔
- Índices de `estrutura[cat]` e `fechado.orcamento[cat].itens` andam juntos (backend preserva ordem das descrições) — a remoção usa o MESMO índice nas duas listas. ✔
- Task 1 muda só a validação/entrada da rota; resposta mantém as chaves que o hub consome. ✔

**Riscos anotados para os revisores:** assinaturas reais do hub (`Tool`, `AgentShell`, `hasToolPermission`, shape do route handler do LUMEN) devem ser conferidas nos arquivos citados antes de transcrever — se divergirem deste plano, o código existente do hub governa.
