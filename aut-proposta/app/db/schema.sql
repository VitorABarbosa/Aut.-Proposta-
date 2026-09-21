-- Tabela de preços (fonte da verdade em runtime; semeada do JSON)
-- Cada categoria pertence a uma `tabela` de preços: "padrao"/"mcmv" (Flying),
-- "rinno" (Rinno Films) e "nid" (NID Studio).
CREATE TABLE IF NOT EXISTS preco_categoria (
    tabela            text NOT NULL DEFAULT 'padrao',
    categoria         text NOT NULL,
    ordem             integer NOT NULL DEFAULT 0,
    rotulo_docx       text NOT NULL DEFAULT '',
    prefixo           text NOT NULL DEFAULT '',
    preco_default     integer,
    descricao_padrao  text,
    CONSTRAINT preco_categoria_pkey PRIMARY KEY (tabela, categoria)
);

CREATE TABLE IF NOT EXISTS preco_item (
    id         serial PRIMARY KEY,
    tabela     text NOT NULL DEFAULT 'padrao',
    categoria  text NOT NULL,
    chave      text NOT NULL,
    descricao  text NOT NULL,
    preco      integer NOT NULL,
    padroes    text[] NOT NULL DEFAULT '{}',
    ordem      integer NOT NULL,
    CONSTRAINT preco_item_tabela_categoria_chave_key UNIQUE (tabela, categoria, chave),
    CONSTRAINT preco_item_tabela_categoria_fkey FOREIGN KEY (tabela, categoria)
        REFERENCES preco_categoria (tabela, categoria) ON DELETE CASCADE
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
    emissor         text NOT NULL DEFAULT 'flying',
    tabela_precos   text NOT NULL DEFAULT 'padrao',
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

-- Migração idempotente para bancos que já tinham o schema anterior (3
-- categorias fixas, sem `tabela`, PK simples em `categoria`). Roda sempre
-- que o schema é aplicado: em banco zerado os CREATE TABLE acima já deixam
-- tudo no shape final e este bloco é um no-op (dropa e recria os mesmos
-- nomes de constraint); em banco antigo, migra de fato.
ALTER TABLE preco_categoria ADD COLUMN IF NOT EXISTS tabela text NOT NULL DEFAULT 'padrao';
ALTER TABLE preco_categoria ADD COLUMN IF NOT EXISTS ordem integer NOT NULL DEFAULT 0;
ALTER TABLE preco_categoria ADD COLUMN IF NOT EXISTS rotulo_docx text NOT NULL DEFAULT '';
ALTER TABLE preco_categoria ADD COLUMN IF NOT EXISTS prefixo text NOT NULL DEFAULT '';
ALTER TABLE preco_categoria ALTER COLUMN preco_default DROP NOT NULL;
ALTER TABLE preco_categoria ALTER COLUMN descricao_padrao DROP NOT NULL;

ALTER TABLE preco_item ADD COLUMN IF NOT EXISTS tabela text NOT NULL DEFAULT 'padrao';

-- Dropa constraints antigas/atuais (nomes conhecidos, default do Postgres
-- para o schema anterior sem CONSTRAINT nomeado explicitamente) antes de
-- recriar no shape final composto por (tabela, categoria).
ALTER TABLE preco_item DROP CONSTRAINT IF EXISTS preco_item_categoria_fkey;
ALTER TABLE preco_item DROP CONSTRAINT IF EXISTS preco_item_tabela_categoria_fkey;
ALTER TABLE preco_item DROP CONSTRAINT IF EXISTS preco_item_categoria_chave_key;
ALTER TABLE preco_item DROP CONSTRAINT IF EXISTS preco_item_tabela_categoria_chave_key;
ALTER TABLE preco_categoria DROP CONSTRAINT IF EXISTS preco_categoria_pkey;

ALTER TABLE preco_categoria ADD CONSTRAINT preco_categoria_pkey PRIMARY KEY (tabela, categoria);
ALTER TABLE preco_item ADD CONSTRAINT preco_item_tabela_categoria_chave_key UNIQUE (tabela, categoria, chave);
ALTER TABLE preco_item ADD CONSTRAINT preco_item_tabela_categoria_fkey
    FOREIGN KEY (tabela, categoria) REFERENCES preco_categoria (tabela, categoria) ON DELETE CASCADE;

ALTER TABLE propostas ADD COLUMN IF NOT EXISTS tabela_precos text NOT NULL DEFAULT 'padrao';

-- Multi-empresa: qual das três empresas do grupo (flying/rinno/nid) emite a
-- proposta. Proposta gravada antes disso é da Flying — o DEFAULT já resolve a
-- coluna nova, e o UPDATE abaixo corrige as que foram feitas na tabela mcmv
-- (também Flying) ou em qualquer tabela de outra empresa, caso o banco já
-- tenha recebido dados novos antes desta migração rodar.
ALTER TABLE propostas ADD COLUMN IF NOT EXISTS emissor text NOT NULL DEFAULT 'flying';
UPDATE propostas SET emissor = 'rinno' WHERE tabela_precos = 'rinno' AND emissor = 'flying';
UPDATE propostas SET emissor = 'nid'   WHERE tabela_precos = 'nid'   AND emissor = 'flying';

-- Registro de cada rodada do chat: o que o usuário mandou, o que a IA chamou
-- e o que respondeu. É a matéria-prima para medir a inteligência — sem isso,
-- toda mudança de prompt é palpite. Nunca derruba o chat: a gravação falha em
-- silêncio (ver app/db/repo_chat_log.py).
CREATE TABLE IF NOT EXISTS chat_log (
    id            serial PRIMARY KEY,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    modelo        text,
    mensagens     jsonb NOT NULL,
    ferramentas   jsonb NOT NULL DEFAULT '[]',
    resposta      jsonb NOT NULL,
    emissor       text,
    duracao_ms    integer,
    erro          text
);
CREATE INDEX IF NOT EXISTS chat_log_criado_em_idx ON chat_log (criado_em DESC);
