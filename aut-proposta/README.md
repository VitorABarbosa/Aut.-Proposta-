# Automação de Proposta — Flying Studio

Serviço FastAPI que gera propostas comerciais em `.docx` timbrado: uma IA
(OpenAI, com fallback regex offline) interpreta o pedido em texto livre, o
código precifica pela tabela oficial (NEON) ou pelo histórico do cliente,
aplica descontos e gera o documento, subindo o arquivo no Cloudflare R2.

**Princípio-chave:** a IA nunca produz um número. Preço, soma e desconto são
código determinístico e testado.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # preencha as variáveis
```

Testes (os de banco usam Postgres local):

```bash
docker compose up -d db-test
pytest
```

Rodar a API:

```bash
uvicorn app.api.main:app --reload
```

Seed da tabela de preços no NEON (uma vez, ou quando a planilha mudar):

```bash
python -m scripts.seed_precos
```

## Rotas

| Rota | Corpo | Faz |
|---|---|---|
| `GET /saude` | — | healthcheck (sem auth) |
| `POST /levantamento` | `{"texto"}` | interpreta + precifica (preview, não grava) |
| `POST /propostas` | `{"texto"}` ou `{"estrutura"}` | grava no NEON, gera `.docx`, sobe no R2 |
| `GET /propostas/{id}/docx` | — | download direto do `.docx` |

Auth: header `Authorization: Bearer $API_TOKEN` em todas menos `/saude`.

## Arquitetura

`app/dominio/` (puro: preços, orçamento, descontos) · `app/db/` (NEON) ·
`app/historico/` (2º levantamento) · `app/ia/` (parser OpenAI/regex) ·
`app/docx/` (gerador timbrado) · `app/storage/` (R2) · `app/servicos/`
(orquestração) · `app/api/` (FastAPI).
