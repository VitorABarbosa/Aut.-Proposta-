# Automação de Proposta — Grupo Flying

Serviço FastAPI que gera propostas comerciais em `.docx` timbrado: uma IA
(OpenAI, com fallback regex offline) interpreta o pedido em texto livre, o
código precifica pela tabela oficial (NEON) ou pelo histórico do cliente,
aplica descontos e gera o documento, subindo o arquivo no Cloudflare R2.

Atende as três empresas do grupo — **Flying Studio**, **Rinno Films** e
**NID Studio** —, cada uma com o seu catálogo, o seu timbrado e a sua estrutura
de documento.

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
| `POST /levantamento` | `{"texto"}` ou `{"estrutura"}` | interpreta + precifica (preview, não grava) |
| `POST /propostas` | `{"texto"}` ou `{"estrutura"}` | grava no NEON, gera `.docx`, sobe no R2 |
| `GET /propostas/{id}/docx` | — | download direto do `.docx` |
| `POST /chat` | `{"mensagens"}` | conversa que monta a proposta (stateless) |

Auth: header `Authorization: Bearer $API_TOKEN` em todas menos `/saude`.

Com `texto`, a empresa vai no corpo (`{"texto": "...", "emissor": "rinno"}`);
com `estrutura`, vai dentro dela (`estrutura.emissor`). Sem nada, é a Flying —
proposta gravada antes do multi-empresa continua sendo dela.

## As três empresas

O campo `emissor` (`flying` | `rinno` | `nid`) decide três coisas, e só elas:
quais tabelas de preço valem, qual timbrado abre o `.docx` e qual gerador
escreve o corpo. Orçamento, desconto, histórico do cliente e persistência são
os mesmos para as três. O registro está em `app/empresas.py`.

| Empresa | Tabelas | Vende | Documento |
|---|---|---|---|
| `flying` | `padrao`, `mcmv` | imagens, plantas, filmes 3D, tour virtual, drone, tecnologias | 3 seções |
| `rinno` | `rinno` | filmes (conceito, produto, viral, institucional, doc) e takes | 4 seções, escopo por filme |
| `nid` | `nid` | interiores, fachada, PDV, apto modelo, produto | 6 seções, fases EP/PRE/EX |

Cuidado com o nome: `emissor` é qual das NOSSAS empresas assina a proposta;
`cliente.empresa` continua sendo a construtora que recebe.

As categorias de Rinno e NID são prefixadas (`rinno_*`, `nid_*`) porque o chat
monta um catálogo único com as três — sem prefixo, `filmes` da Flying e
`filmes` da Rinno colidiriam no schema da ferramenta. As da Flying seguem sem
prefixo: são as que já estão gravadas nas propostas antigas.

Uma proposta é de UMA empresa. Pedido que mistura serviços de duas (imagens +
filme) vira duas propostas — o chat avisa e pergunta por qual começar.

### Preço fora da planilha

A planilha é ponto de partida, não regra. Dois campos da estrutura cobrem as
práticas da casa, e os dois entram no preço de cada item — por isso **não
aparecem na proposta**, ao contrário do desconto, que é linha visível:

- `ajuste_planilha_pct`: "planilha + 10%" (costume para cliente novo) ou
  "planilha − 5%". Fachada 3.000 vira 3.300; a fonte do item registra
  `planilha+10%:fachada`.
- `preco_por_imagem`: o cliente fecha um valor único para todas as
  perspectivas e plantas (OUSY a 2.200, UNICOS a 2.400), seja fachada ou voo
  de pássaro. Só afeta categorias de imagem; filme, tour e tecnologia seguem
  na tabela. Passa por cima do histórico também.

Proposta de cortesia (desconto de 100%) imprime **CORTESIA** no investimento,
como a Rinno faz, em vez de "R$ 0,00".

### Categoria certa para a empresa certa

O chat oferece `filmes` (Flying) e `rinno_filmes` lado a lado e o modelo às
vezes pega a chave curta mesmo com o emissor certo. `levantar` remapeia
categoria sem prefixo para o namespace do emissor (`filmes` → `rinno_filmes`,
`fachada` → `nid_fachada`) antes de precificar — só para dentro da própria
empresa, nunca de uma para outra — e devolve a estrutura já corrigida.

### Medindo a inteligência

O chat roda no modelo definido em `OPENAI_MODEL` (default `gpt-4o-mini`) com
**uma ferramenta de precificação por empresa** — `precificar_flying`,
`precificar_rinno`, `precificar_nid` —, cada uma só com as categorias e tabelas
da própria. Escolher a ferramenta é escolher a empresa; categoria de outra
empresa deixa de ser possível. O prompt traz exemplos tirados de propostas
reais, e todo erro de ferramenta é repassado ao usuário como está.

Toda rodada fica em `chat_log` (mensagens, chamadas de ferramenta, resposta,
modelo, duração). Conversa que deu errado vira um **caso-ouro** em
`tests/ia/casos/*.json`: os turnos do usuário e o que a última chamada de
precificação precisa conter. O avaliador roda todos contra o modelo de verdade:

```bash
DATABASE_URL=... OPENAI_API_KEY=... python -m scripts.avaliar_chat
OPENAI_MODEL=<outro modelo> python -m scripts.avaliar_chat   # comparar modelos
python -m scripts.avaliar_chat archtech_viral_4k             # um caso só
```

Sem isso, mudança de prompt ou de modelo é palpite; com isso, é número.
Regra: caso novo entra junto com a correção, e nenhuma mudança no chat sobe
com a nota caindo.

### Como o item aparece escrito

Categoria com prefixo de escrita é imagem: cada cena é diferente, então o texto
do usuário é preservado ("Fachada vista da calçada" → "Perspectiva Fachada
vista da calçada"). Categoria sem prefixo é serviço de catálogo — filme, tour,
projeto: sai com o nome comercial oficial, não como foi digitado na pressa
("filme corretor" → "Filme Corretor / Produto de até 1:30"). Exceto quando o
texto já traz duração ou número ("filme institucional de até 2:00"): aí a
redação do usuário fica, porque a duração foi fechada com o cliente.

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
token. A resposta devolve em `transcricao` exatamente o texto que foi para o
modelo — o front grava isso no lugar da imagem e para de reenviar o base64.

Item que não casa claramente com o catálogo nunca é chutado numa categoria:
vai para as dúvidas da transcrição e o chat pergunta.

## Arquitetura

`app/empresas.py` (as três empresas) · `app/dominio/` (puro: preços,
orçamento, descontos) · `app/db/` (NEON) · `app/historico/` (2º levantamento) ·
`app/ia/` (parser OpenAI/regex, chat, leitura de print) · `app/docx/`
(`base.py` + um gerador por empresa) · `app/storage/` (R2) · `app/servicos/`
(orquestração) · `app/api/` (FastAPI).
