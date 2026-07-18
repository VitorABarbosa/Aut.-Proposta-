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
