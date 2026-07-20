# Plano 6 — Catálogo completo 2026, MCMV e IA rígida — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** cobrir TODOS os serviços Flying Studio da Planilha_PRECOS_2026 (18 itens em 8 categorias), com tabela alternativa MCMV, categorias dinâmicas vindas do NEON (domínio → docx → chat → hub), e IA rígida: serviço fora do catálogo → pergunta, nunca chuta.

**Architecture:** categorias deixam de ser as 3 fixas e passam a vir de `preco_categoria` (com `tabela`, `ordem`, `rotulo_docx`, `prefixo`). O shape da `estrutura`/orçamento CONTINUA com categorias como chaves planas top-level (compatibilidade); o dict do orçamento ganha a chave meta `"_categorias": [{"nome","rotulo"}...]` (ordenada) que docx e hub passam a iterar. `estrutura` ganha `tabela_precos: "padrao"|"mcmv"`. O catálogo (nomes, sem preços) é injetado no SYSTEM_PROMPT do chat; schema da tool gerado dinamicamente.

**Tech Stack:** o existente. Branches: backend `feat/plano-6-catalogo`; hub `feat/proposta-plano-6` (worktree `.worktrees/proposta-chat`).

## Global Constraints

- A IA nunca produz número; preços só via `levantar`.
- **Rigidez**: pedido que não casa claramente com item do catálogo → a IA PERGUNTA (citando 2-3 candidatos do catálogo), nunca encaixa por palpite. Ex. real: "Aplicativo" deve ir para `tecnologia/app_web_touch`, jamais para imagem interna.
- Compatibilidade: categorias continuam chaves planas na `estrutura` e no `orcamento` do `fechado`; consumidores antigos não quebram. `_categorias` é aditivo.
- Ordem determinística das categorias via coluna `ordem` (numeração 2.N do docx).
- `proposta_itens.categoria` já é text livre — propostas antigas continuam legíveis; `repo_propostas` NÃO pode mais descartar categorias desconhecidas (bug latente L72/L109).
- Migração em NEON prod é ALTER (não drop): dados de propostas existentes preservados; `preco_*` é re-semeado (DELETE+INSERT).
- Testes: db com `@pytest.mark.db`+fixture `db`; sem rede; hub Jest.

## Catálogo (fonte: Planilha_PRECOS_2026.xlsx, só Flying; App Web e Explorador D.Brave são Flying)

Arquivo novo versionado `aut-proposta/app/dados/precos_2026.json` — shape:
```json
{"padrao": {"categorias": [
  {"nome": "externas", "ordem": 1, "rotulo": "Ilustrações Externas", "prefixo": "Perspectiva ",
   "default": 1900, "descricao_padrao": "Perspectiva Externa Diversa", "itens": [
    {"chave": "fachada", "descricao": "Perspectiva Fachada / Fotomontagem / Voo", "preco": 3000, "padroes": ["fachada", "portaria", "fotomontagem(?! ?/? ?com foto ?drone)", "voo(?!\\s+de\\s+passaro)"]},
    {"chave": "fotomontagem_drone", "descricao": "Fotomontagem com FotoDrone (por conta da Flying)", "preco": 4500, "padroes": ["foto ?drone", "fotomontagem com drone"]},
    {"chave": "voo_passaro", "descricao": "Perspectiva Voo de Pássaro", "preco": 2500, "padroes": ["voo de passaro", "passaro"]},
    {"chave": "externa_diversa", "descricao": "Perspectiva Externa Diversa", "preco": 1900, "padroes": ["externa", "playground", "piscina", "quadra", "terraco", "praça", "praca"]}]},
  {"nome": "internas", "ordem": 2, "rotulo": "Ilustrações Internas", "prefixo": "Perspectiva ",
   "default": 1750, "descricao_padrao": "Perspectiva Interna Diversa", "itens": [
    {"chave": "interna_diversa", "descricao": "Perspectiva Interna Diversa", "preco": 1750, "padroes": ["interna", "academia", "salao", "salão", "coworking", "lavanderia", "market", "cozinha", "dormitorio", "dormitório"]}]},
  {"nome": "plantas", "ordem": 3, "rotulo": "Plantas Humanizadas 2D", "prefixo": "Planta Humanizada ",
   "default": 1200, "descricao_padrao": "Planta Humanizada Tipo", "itens": [
    {"chave": "planta_pavimentos", "descricao": "Planta Humanizada Pavimentos (Térreo, Rooftop, Estacionamento)", "preco": 3000, "padroes": ["implanta", "pavimento", "terreo", "térreo", "rooftop", "estacionamento", "subsolo"]},
    {"chave": "planta_isometrica", "descricao": "Planta Tipo Isométrica 3D", "preco": 1900, "padroes": ["isometrica", "isométrica", "planta.*3d"]},
    {"chave": "planta_tipo", "descricao": "Planta Humanizada Tipo", "preco": 1200, "padroes": ["tipo", "planta"]}]},
  {"nome": "filmes", "ordem": 4, "rotulo": "Filmes e Takes 3D", "prefixo": "",
   "default": 15000, "descricao_padrao": "Filme 3D — 60 segundos", "itens": [
    {"chave": "filme_3d_60s", "descricao": "Filme 3D — 60 segundos", "preco": 15000, "padroes": ["filme"]},
    {"chave": "takes_7s", "descricao": "Take 3D de até 7 segundos", "preco": 1300, "padroes": ["take"]}]},
  {"nome": "tour_virtual", "ordem": 5, "rotulo": "Tour Virtual / VR 360", "prefixo": "",
   "default": 1200, "descricao_padrao": "Tour Virtual 360 — Render por ambiente", "itens": [
    {"chave": "tour_elaboracao", "descricao": "Tour Virtual / VR 360 Multiplataforma — Elaboração, por ambiente", "preco": 2500, "padroes": ["elabora"]},
    {"chave": "tour_render", "descricao": "Tour Virtual / VR 360 Multiplataforma — Render, por ambiente", "preco": 1200, "padroes": ["render"]},
    {"chave": "tour_web", "descricao": "Tour Virtual / VR 360 Multiplataforma — Web/Mobile/PC, por ambiente", "preco": 450, "padroes": ["web", "mobile", "publica"]}]},
  {"nome": "drone", "ordem": 6, "rotulo": "Drone e Fotografia Aérea", "prefixo": "",
   "default": 2200, "descricao_padrao": "Fotografia Aérea Drone — para Fotomontagem", "itens": [
    {"chave": "foto_aerea", "descricao": "Fotografia Aérea Drone — para Fotomontagem", "preco": 2200, "padroes": ["fotografia", "aerea", "aérea"]},
    {"chave": "voo_drone_hora", "descricao": "Voo de Drone — por hora, por endereço (SP)", "preco": 1800, "padroes": ["voo de drone", "hora"]}]},
  {"nome": "estudos", "ordem": 7, "rotulo": "Estudos de Fachada", "prefixo": "",
   "default": 18000, "descricao_padrao": "Estudo de Fachada / Cromático", "itens": [
    {"chave": "estudo_fachada", "descricao": "Estudo de Fachada / Cromático de Fachada", "preco": 18000, "padroes": ["estudo", "cromatico", "cromático"]}]},
  {"nome": "tecnologia", "ordem": 8, "rotulo": "Tecnologias Interativas", "prefixo": "",
   "default": 22800, "descricao_padrao": "Desenvolvimento de Aplicação Web para Tela Touch", "itens": [
    {"chave": "app_web_touch", "descricao": "Desenvolvimento de Aplicação Web — para Tela Touch", "preco": 22800, "padroes": ["aplicativo", "aplicacao", "aplicação", "app", "touch"]},
    {"chave": "explorador_dbrave", "descricao": "Explorador D.Brave", "preco": 39000, "padroes": ["explorador", "d\\.?brave"]}]}
]},
 "mcmv": {"categorias": [
  {"nome": "externas", "ordem": 1, "rotulo": "Ilustrações Externas", "prefixo": "Perspectiva ",
   "default": 1850, "descricao_padrao": "Perspectiva Externa Diversa", "itens": [
    {"chave": "fotomontagem_interno", "descricao": "Fotomontagem — com projeto interno", "preco": 3500, "padroes": ["fotomontagem.*interno"]},
    {"chave": "fotomontagem_externo", "descricao": "Fotomontagem — com projeto externo", "preco": 4500, "padroes": ["fotomontagem"]},
    {"chave": "fachada", "descricao": "Perspectiva Fachada / Portaria", "preco": 2800, "padroes": ["fachada", "portaria"]},
    {"chave": "voo_passaro", "descricao": "Perspectiva Voo de Pássaro", "preco": 1900, "padroes": ["voo de passaro", "passaro"]},
    {"chave": "externa_diversa", "descricao": "Perspectiva Externa Diversa", "preco": 1850, "padroes": ["externa", "playground", "piscina", "quadra"]}]},
  {"nome": "internas", "ordem": 2, "rotulo": "Ilustrações Internas", "prefixo": "Perspectiva ",
   "default": 1500, "descricao_padrao": "Perspectiva Interna Diversa", "itens": [
    {"chave": "interna_diversa", "descricao": "Perspectiva Interna Diversa", "preco": 1500, "padroes": ["interna", "academia", "salao", "salão", "cozinha"]}]},
  {"nome": "plantas", "ordem": 3, "rotulo": "Plantas Humanizadas 2D", "prefixo": "Planta Humanizada ",
   "default": 900, "descricao_padrao": "Planta Humanizada Tipo", "itens": [
    {"chave": "planta_pavimentos", "descricao": "Planta Pavimentos (Térreo, Rooftop, Estacionamento)", "preco": 2000, "padroes": ["implanta", "pavimento", "terreo", "térreo", "rooftop", "subsolo"]},
    {"chave": "planta_isometrica", "descricao": "Planta Tipo Isométrica 3D", "preco": 1850, "padroes": ["isometrica", "isométrica", "planta.*3d"]},
    {"chave": "planta_tipo", "descricao": "Planta Tipo", "preco": 900, "padroes": ["tipo", "planta"]}]},
  {"nome": "filmes", "ordem": 4, "rotulo": "Filmes e Takes 3D", "prefixo": "",
   "default": 11500, "descricao_padrao": "Filme 3D — 60 segundos", "itens": [
    {"chave": "filme_3d_60s", "descricao": "Filme 3D — 60 segundos", "preco": 11500, "padroes": ["filme"]},
    {"chave": "takes", "descricao": "Takes", "preco": 1250, "padroes": ["take"]}]},
  {"nome": "tour_virtual", "ordem": 5, "rotulo": "Tour Virtual / VR 360", "prefixo": "",
   "default": 1200, "descricao_padrao": "Tour Virtual 360 — Render por ambiente", "itens": [
    {"chave": "tour_elaboracao", "descricao": "Tour Virtual / VR 360 Multiplataforma — Elaboração, por ambiente", "preco": 2500, "padroes": ["elabora"]},
    {"chave": "tour_render", "descricao": "Tour Virtual / VR 360 Multiplataforma — Render, por ambiente", "preco": 1200, "padroes": ["render"]},
    {"chave": "tour_web", "descricao": "Tour Virtual / VR 360 Multiplataforma — Web/Mobile/PC, por ambiente", "preco": 450, "padroes": ["web", "mobile"]}]},
  {"nome": "drone", "ordem": 6, "rotulo": "Drone e Fotografia Aérea", "prefixo": "",
   "default": 2100, "descricao_padrao": "Fotografia Aérea — para Fotomontagem", "itens": [
    {"chave": "foto_aerea", "descricao": "Fotografia Aérea — para Fotomontagem", "preco": 2100, "padroes": ["fotografia", "aerea", "aérea"]},
    {"chave": "voo_drone_hora", "descricao": "Voo de Drone — por hora, por endereço (SP)", "preco": 2100, "padroes": ["voo de drone", "hora"]}]},
  {"nome": "estudos", "ordem": 7, "rotulo": "Estudos de Fachada", "prefixo": "",
   "default": 11500, "descricao_padrao": "Estudo de Fachada / Cromático", "itens": [
    {"chave": "estudo_fachada", "descricao": "Estudo de Fachada / Cromático de Fachada", "preco": 11500, "padroes": ["estudo", "cromatico", "cromático"]}]}
]}}
```
(Ordem dos itens dentro da categoria importa: 1º match ganha, específico antes do genérico.)

---

### Task 1: Schema + seed + migração (backend)

**Files:** Modify `app/db/schema.sql`, `scripts/seed_precos.py`, `app/db/repo_precos.py`; Create `app/dados/precos_2026.json` (verbatim acima), `scripts/migrar_catalogo_2026.py`; Test: `tests/db/test_repo_precos.py`, `tests/db/test_seed_precos.py`.

**Schema (DDL alvo):** `preco_categoria(tabela text NOT NULL DEFAULT 'padrao', categoria text, ordem int NOT NULL DEFAULT 0, rotulo_docx text NOT NULL DEFAULT '', prefixo text NOT NULL DEFAULT '', preco_default int, descricao_padrao text, PRIMARY KEY (tabela, categoria))`; `preco_item` ganha `tabela text NOT NULL DEFAULT 'padrao'`, FK composta `(tabela, categoria)`, UNIQUE `(tabela, categoria, chave)`; `propostas` ganha `tabela_precos text NOT NULL DEFAULT 'padrao'`.

**Interfaces produzidas:**
- `carregar_tabela_precos(conn, tabela: str = "padrao") -> dict` — shape por categoria ganha metadados: `dados[categoria] = {"_default", "_descricao_padrao", "_ordem", "_rotulo", "_prefixo", "tabela": [...]}` (itens como hoje). Sem `setdefault` das 3 fixas: devolve o que existe no banco, na ordem de `_ordem`.
- `semear_precos(conn)` — lê `precos_2026.json`, DELETE em `preco_item`/`preco_categoria` e insere as DUAS tabelas (padrao+mcmv).
- `scripts/migrar_catalogo_2026.py` — idempotente, roda em prod: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, recria PK/FK/UNIQUE compostas (com DO $$ / drop constraint if exists), depois chama `semear_precos` e commita. Usa `DATABASE_URL` do ambiente.

**Steps:** testes primeiro (categorias novas presentes com meta e ordem; mcmv carrega preços próprios; migração idempotente rodando 2x no db-test), implementar, suíte verde, commit `feat(proposta): catálogo 2026 completo no schema (tabelas padrao/mcmv, categorias com meta)`.

---

### Task 2: Domínio dinâmico (backend)

**Files:** Modify `app/dominio/precos.py`, `app/dominio/orcamento.py`, `app/historico/orcamento_historico.py`, `app/historico/historico.py`, `app/db/repo_propostas.py`, `app/servicos/proposta.py`; Tests dos módulos correspondentes.

**Interfaces:**
- `TabelaPrecos` expõe `categorias() -> list[str]` (ordenada por `_ordem`) e `meta(categoria) -> {"rotulo","prefixo","ordem"}`; `classificar` valida contra `self.dados.keys()`. Prefixos deixam de ser constantes: `_formata_descricao` usa `meta(cat)["prefixo"]` (fallback "" p/ categoria sem prefixo; `_PREFIXOS_JA_ESCRITOS` vira derivado do prefixo: se a descrição já começa com a 1ª palavra do prefixo, não duplica).
- `Orcamento` refatorado: `categorias: dict[str, CategoriaOrcada]` (ordenado) + `estrategia`; `subtotal`/`total_imagens` somam o dict; `to_dict()` emite cada categoria como chave plana top-level (compat) MAIS `"_categorias": [{"nome","rotulo"}...]` na ordem. `orcar_pela_planilha(descricoes, tabela)` itera `tabela.categorias()`.
- `orcar_pelo_historico`/`historico.py`: categorias derivadas das linhas da proposta histórica (não constante). `medias_por_categoria` idem.
- `repo_propostas`: `salvar_proposta` itera as categorias do `orc` (dinâmico, ignora chaves iniciadas por "_" e as não-dict); `ultima_proposta_estruturada` e `obter_estrutura_de_proposta` NÃO descartam categorias desconhecidas — montam a partir do SELECT; `obter_estrutura_de_proposta` inclui `tabela_precos` da proposta; `salvar_proposta` grava `tabela_precos` (novo parâmetro, default "padrao").
- `servicos/proposta.py`: `_descricoes(estrutura, categorias)` dinâmico; `levantar` lê `tabela = estrutura.get("tabela_precos") or "padrao"` (validar em {"padrao","mcmv"}, senão ValueError), carrega a tabela certa e devolve também `"tabela_precos": tabela` no dict; `gerar` repassa ao salvar.
- CATEGORIAS constantes: remover as 5 redefinições; onde precisar de fallback estático (sem conn), usar `("externas","internas","plantas")` apenas em compat de leitura antiga.

**Steps:** TDD por módulo (casos novos: orçamento com filmes+tecnologia soma e ordena; item "Aplicação Web Touch" classifica em tecnologia 22800; mcmv precifica interna a 1500; proposta salva com categoria "filmes" e relida sem descarte), suíte inteira verde, commit `feat(proposta): categorias dinâmicas no domínio e tabela MCMV`.

---

### Task 3: Docx dinâmico (backend)

**Files:** Modify `app/docx/gerador.py`; Test `tests/docx/test_gerador.py`.

Seção 2 itera `orc["_categorias"]` (ordem do banco), pulando `qtd==0`; subtítulo `2.{sub} {rotulo}`; fallback: sem `_categorias`, usa as 3 fixas com `ROTULOS_CATEGORIA` atual (propostas antigas re-geradas). Investimento/pagamento continuam auto-renumerando. Título da capa e textos fixos inalterados. Testes: proposta com filmes+tecnologia gera seções "2.4 Filmes e Takes 3D"/"2.5 Tecnologias Interativas" (com 3 categorias de imagem presentes) e renumera investimento; fidelidade dos destaques do modelo permanece (testes existentes passam sem alteração de conteúdo fixo).

Commit `feat(proposta): docx com seções dinâmicas por categoria`.

---

### Task 4: Chat e parser cientes do catálogo + rigidez + MCMV (backend)

**Files:** Modify `app/ia/chat.py`, `app/ia/parser.py`, `app/servicos/proposta.py` (se precisar passar categorias ao parser), `app/api/main.py` (nada esperado); Tests `tests/ia/test_chat.py`, `tests/ia/test_parser.py`.

- `chat.py`: `_schema_estrutura(categorias: list[str])` gera as propriedades das listas dinamicamente + `tabela_precos: {"type":"string","enum":["padrao","mcmv"]}`; `_montar_system_prompt(catalogo)` injeta o catálogo (por categoria: rotulo + descrições dos itens, SEM preços) e as regras verbatim:
  - "CATÁLOGO OFICIAL (única fonte de classificação): {...}"
  - "REGRA DE RIGIDEZ: se o pedido não casar claramente com um item do catálogo acima, NÃO classifique por palpite. Pergunte ao usuário qual item corresponde, citando 2-3 candidatos do catálogo. Um serviço que não é imagem NUNCA entra como ilustração externa/interna."
  - "MCMV: se o usuário indicar que o empreendimento é Minha Casa Minha Vida (MCMV/faixa/raiz), use tabela_precos='mcmv'. Na dúvida, pergunte."
  - Mantém: formato texto simples sem markdown/links.
  - `responder` carrega o catálogo do conn 1x por request (`carregar_tabela_precos(conn)`) para montar prompt+schema; `_completar_estrutura(bruto, categorias)` usa as categorias dinâmicas e preserva `tabela_precos` válida.
- `parser.py`: `parse(texto, cliente_padrao..., categorias: list[str] | None = None)` — `SECOES_CABEC`/defaults/complemento gerados de `categorias` (fallback 3 fixas); prompt OpenAI do parser lista as categorias ativas. `levantar` passa as categorias da tabela carregada.
- Testes: schema contém "filmes"/"tecnologia"; `_completar_estrutura` preserva `tabela_precos:"mcmv"`; prompt contém "REGRA DE RIGIDEZ" e o rótulo "Tecnologias Interativas"; parser com categorias extras reconhece cabeçalho "Filmes:".

Commit `feat(proposta): chat com catálogo oficial, regra de rigidez e MCMV`.

---

### Task 5: Hub dinâmico + seletor MCMV

**Files (worktree):** Modify `src/components/agents/proposta/types.ts`, `PreviewPainel.tsx`, `EntradaPainel.tsx` (placeholder), tests.

- `types.ts`: `CategoriaKey = string`; `Estrutura` com campos conhecidos + `tabela_precos?: 'padrao' | 'mcmv'` + index signature p/ categorias (`[categoria: string]: unknown`); `Fechado['orcamento']` ganha `_categorias?: {nome: string; rotulo: string}[]` e index p/ `CategoriaOrcada`.
- `PreviewPainel`: itera `fechado.orcamento._categorias ?? [3 fixas c/ rótulos atuais]`; estado `novos` derivado dinamicamente; novo select "Tabela" (Padrão | MCMV) ao lado de Estratégia — muda `estrutura.tabela_precos` e reprecifica (mesmo padrão commit do select de estratégia).
- Teste: preview renderiza categoria extra ("Filmes e Takes 3D") vinda de `_categorias`; select de tabela dispara reprecificar com `tabela_precos:'mcmv'`.

Commit `feat(proposta): preview com categorias dinâmicas e seletor MCMV`.

---

### Task 6: Migração prod + E2E real (controlador)

`python scripts/migrar_catalogo_2026.py` contra NEON prod (DATABASE_URL do .env); E2E real OpenAI: "quero um aplicativo touch para o stand" → classifica tecnologia/22800 OU pergunta se ambíguo; "3 fachadas MCMV" → tabela mcmv (fachada 2800); serviço inexistente ("quero um jingle") → pergunta, não classifica. Registrar no ledger.

## Self-Review

- Itens do user: (1) reset chat — já feito fora do plano (hub 571226b); (2) catálogo completo + MCMV + rigidez → Tasks 1-4 + 6; (3) links/formatação — já feito (backend 5cccf19). ✔
- Consistência: `_categorias` produzido por `Orcamento.to_dict` (T2) é consumido por docx (T3) e hub (T5); `tabela_precos` flui estrutura→levantar→salvar→obter_estrutura (T2) e chat (T4) e hub (T5); shape plano preservado em todas as camadas. ✔
- Armadilhas do mapa endereçadas: 5 redefinições de CATEGORIAS removidas (T2), descarte silencioso corrigido (T2), ordem determinística (T1 `ordem`), additionalProperties do schema (T4 dinâmico), PreviewPainel iterando fonte fixa (T5). ✔
