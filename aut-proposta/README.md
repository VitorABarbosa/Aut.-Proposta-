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
| `POST /chat` | `{"mensagens"}` | conversa que monta a proposta (stateless) |

Auth: header `Authorization: Bearer $API_TOKEN` em todas menos `/saude`.

## Print no chat

O `content` de uma mensagem pode vir em partes, como na OpenAI, com o print
anexado em base64:

```json
{"role": "user", "content": [
  {"type": "text", "text": "monta a proposta desse e-mail"},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
]}
```

O print é lido **uma única vez**: a imagem passa pelas guardas de entrada
(máx. 5 MB e 4 prints por mensagem, formato conferido pela assinatura do
arquivo, downscale para 1400 px no maior lado) e vira uma transcrição em texto
com construtora, empreendimento, A/C, itens e dúvidas. Da segunda rodada em
diante a transcrição sai do cache e o que segue para o modelo é só texto — o
front reenvia o histórico inteiro a cada mensagem, e imagem custa caro em
token. A resposta devolve essa transcrição em `transcricao`, para o front
poder parar de reenviar o base64.

Item que não casa claramente com o catálogo nunca é chutado numa categoria:
vai para as dúvidas da transcrição e o chat pergunta.

## Arquitetura

`app/dominio/` (puro: preços, orçamento, descontos) · `app/db/` (NEON) ·
`app/historico/` (2º levantamento) · `app/ia/` (parser OpenAI/regex, chat,
leitura de print) · `app/docx/` (gerador timbrado) · `app/storage/` (R2) ·
`app/servicos/` (orquestração) · `app/api/` (FastAPI).
