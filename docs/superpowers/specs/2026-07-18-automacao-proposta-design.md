# Design — Automação de Proposta Flying Studio

**Data:** 2026-07-18
**Status:** Aprovado (aguardando plano de implementação)

## 1. Objetivo

Serviço que gera **propostas comerciais Flying Studio** em `.docx` (padrão da
`ITENS_PROPOSTA/PROPOSTA_EXEMPLO.doc`), guiado por uma IA de chat que pergunta cada item
flexível ao usuário, precifica com base na tabela oficial e no histórico do cliente, soma
tudo, aplica descontos e gera o documento final no papel timbrado.

Consumido pelo hub interno (`flyingstudio-tools`, Next.js) via API, no mesmo padrão de
integração de LUMEN e PESQUISADOR.

## 2. Decisões (aprovadas)

| Decisão | Escolha |
|---|---|
| Onde vive | Serviço próprio (padrão LUMEN) + só a UI no hub |
| Backend | Python FastAPI + Docker (deploy Railway) |
| Papel da IA | IA conversa/classifica; **código** calcula soma/preços/descontos |
| Provedor LLM | **OpenAI (ChatGPT)** |
| Natureza das imagens | Itens de orçamento (render a produzir); sem upload de arquivos |
| Saída | `.docx` timbrado (PDF fica para depois) |
| Dados estruturados | NEON Postgres (clientes, propostas, itens, tabela de preços) |
| Arquivos gerados | Cloudflare R2 (.docx), URL salva no NEON |
| Fluxo de UI | Chat + preview ao vivo (tela dividida) |

**Princípio-chave:** o LLM **nunca** produz um número. Ele interpreta linguagem
("5 internas, 3 fachadas") e devolve itens estruturados. Preço vem da tabela (NEON) ou do
histórico; soma e descontos são código puro e testável.

**Reaproveitamento:** a versão antiga (`AUT_PROPOSTA/Aut_proposta_old/Flying-studio-proposta`)
já tem lógica madura a portar — `flying/orcamento.py` (2 levantamentos), `flying/precos.py`
(classificador por regex), `flying/historico.py`, `flying/docx_writer.py`, e `flying/ai_parser.py`
(OpenAI + fallback regex). Os JSONs `data/precos_planilha.json` e `data/historico_clientes.json`
são a base do seed do NEON.

## 3. Arquitetura

```
HUB (flyingstudio-tools, Next.js)
  src/components/agents/proposta/   (só a UI)
    ├─ ChatPanel      conversa com a IA
    └─ PreviewPanel   proposta ao vivo + total
        │ HTTPS (API REST, autenticado pelo hub)
        ▼
SERVIÇO aut-proposta (FastAPI)
  api/         rotas HTTP + validação (Pydantic) + auth
  ia/          conversa (OpenAI) + extração de itens (fallback regex local)
  dominio/     precos · orcamento · descontos
  historico/   consulta propostas passadas do cliente
  docx/        geração do .docx timbrado (HEADER/FOOTER/marca d'água)
  db/          repositórios NEON
  storage/     upload do .docx no Cloudflare R2
        │                         │
   NEON Postgres (dados)     Cloudflare R2 (.docx)
```

## 4. Módulos do backend

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `api/` | Rotas HTTP, validação, auth do hub | ia, dominio, docx |
| `ia/` | Interpreta fala → itens estruturados; conduz perguntas dos itens flexíveis | OpenAI |
| `dominio/precos` | Classifica item e retorna preço da tabela (lookup por regex) | db |
| `dominio/orcamento` | 2 levantamentos (Tabela × Histórico), soma por categoria | precos, historico |
| `dominio/descontos` | Aplica descontos (%, valor fixo, parceria) sobre o subtotal | — |
| `historico/` | Consulta propostas passadas para reaplicar preços | db |
| `docx/` | Gera `.docx` timbrado com conteúdo fixo + itens flexíveis | — |
| `db/` | Repositórios NEON | — |
| `storage/` | Sobe `.docx` no R2, devolve URL; grava no NEON | — |

**Conteúdo fixo** (Tópico 1 Apresentação; Tópico 3 Prazos/Solicitações/Considerações/Entregas):
templates versionados no serviço.
**Conteúdo flexível** (nome construtora/incorporadora; Tópico 2 itens/investimentos): vem do chat.

## 5. Modelo de dados (NEON)

```
clientes(id, nome, contato, criado_em)

propostas(id, cliente_id, referencia, data, status,
          subtotal, desconto_pct, desconto_valor, total,
          docx_url,                 -- aponta pro R2
          criado_em)

proposta_itens(id, proposta_id, categoria, descricao, preco,
               origem)             -- 'tabela' | 'historico' | 'manual'

tabela_precos(id, categoria, chave, descricao, preco, padroes[])
              -- seed da Planilha_PRECOS_2026.xlsx + precos_planilha.json
```

A IA consulta histórico via `SELECT` (últimas propostas do cliente + preços praticados). O
preview mostra tudo antes de gerar.

## 6. Fluxo de uma proposta

1. Usuário abre a ferramenta no hub → sessão/rascunho criada no NEON.
2. IA pergunta item flexível a item flexível: nome do cliente → externas → internas →
   fachadas → plantas → extras.
3. A cada resposta: `ia/` extrai itens → `dominio/precos` precifica (com sugestão do
   `historico/` se o cliente já existe) → preview atualiza ao vivo, total correndo.
4. Ao final, controles de desconto (parceria %, valor fixo) recalculam o total — por código.
5. "Gerar .docx" → `docx/` monta (fixo + flexível) → `storage/` sobe no R2 → grava proposta
   final no NEON → hub oferece o download.

## 7. Tratamento de erros

- **OpenAI indisponível:** fallback para o parser regex local (já existe); IA vira "modo manual".
- **Item não classificado:** cai no preço `_default` da categoria e sinaliza no preview para revisão.
- **R2 falhando:** `.docx` ainda é oferecido para download direto e reenviado depois.

## 8. Testes (pytest, padrão LUMEN)

- Núcleo de `dominio/` (precificação, soma, descontos) com cobertura alta e **casos reais** das
  propostas antigas (ex: GALLI) — é onde mora o dinheiro.
- `docx/` valida que o documento gerado bate com a `PROPOSTA_EXEMPLO`.

## 9. Fora de escopo (por ora)

- Upload/análise de plantas ou imagens de referência.
- Geração de PDF.
- Edição colaborativa multi-usuário simultânea.

## 10. Referências no repositório

- Proposta modelo: `ITENS_PROPOSTA/PROPOSTA_EXEMPLO.doc`
- Timbrado: `ITENS_PROPOSTA/HEADER.jpeg`, `FOOTER.jpeg`, `MARCA D AGUA.jpeg`
- Tabela de preços: `ITENS_PROPOSTA/Planilha_PRECOS_2026.xlsx`
- Lógica a portar: `Aut_proposta_old/Flying-studio-proposta/flying/*`
- Dados-base: `Aut_proposta_old/Flying-studio-proposta/data/*.json`
- Padrão de serviço: `../LUMEN` (FastAPI + Docker + Railway + pytest)
- Padrão de integração no hub: `../SITES/.../flyingstudio-tools/src/components/agents/`
