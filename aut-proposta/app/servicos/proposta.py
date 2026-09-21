"""Orquestração de uma proposta: NEON -> orçamento -> .docx -> R2 -> NEON.

Único lugar que decide a estratégia (planilha × histórico) e o único caminho
de produção que monta TabelaPrecos — sempre via carregar_tabela_precos(conn).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from app.db.repo_precos import carregar_tabela_precos
from app.db.repo_propostas import atualizar_docx_url, salvar_proposta, upsert_cliente
from app.docx.gerador import gerar_docx
from app.dominio.descontos import Desconto
from app.dominio.orcamento import (
    CategoriaOrcada,
    ItemOrcado,
    Orcamento,
    e_categoria_por_ambiente,
    entrada_de_item,
    fechar_orcamento,
    orcar_pela_planilha,
)
from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar
from app.empresas import EMISSORES
from app.empresas import empresa as empresa_emissora
from app.empresas import resolver_tabela
from app.historico.historico import Historico
from app.historico.orcamento_historico import orcar_pelo_historico
from app.storage.r2 import enviar_docx


def parse_texto(conn: psycopg.Connection, texto: str,
                emissor: str | None = None) -> dict[str, Any]:
    """Converte texto livre em estrutura, usando as categorias da empresa
    emissora (o `texto` não indica ainda qual das tabelas dela usar)."""
    from app.ia.parser import parse

    emp = empresa_emissora(emissor)
    tabela = carregar_tabela_precos(conn, emp.tabela_padrao)
    estrutura = parse(texto, categorias=tabela.categorias())
    estrutura["emissor"] = emp.chave
    estrutura["tabela_precos"] = emp.tabela_padrao
    return estrutura


def _slug(texto: str) -> str:
    """Normaliza e converte espaços em hífens para slug de chave R2."""
    return normalizar(texto).replace(" ", "-")


def _descricoes(estrutura: dict[str, Any], categorias: list[str]) -> dict[str, list[str]]:
    return {cat: estrutura.get(cat, []) for cat in categorias}


def no_namespace_do_emissor(estrutura: dict[str, Any], emissor: str,
                            categorias: list[str]) -> dict[str, Any]:
    """Move itens de categoria sem prefixo para a categoria da empresa.

    O schema da ferramenta do chat oferece `filmes` (Flying) e `rinno_filmes`
    lado a lado, e o modelo pega a chave curta mesmo com o emissor certo — foi
    o que aconteceu com "filme institucional para a Archtech": emissor rinno,
    item em `filmes`, e a proposta saiu sem preço. Aqui isso vira
    `rinno_filmes` sem depender de o modelo acertar. Só entra no namespace
    do próprio emissor; nunca cruza de uma empresa para outra.
    """
    saida = dict(estrutura)
    for cat, itens in estrutura.items():
        if cat.startswith("_") or cat in categorias or not isinstance(itens, list) or not itens:
            continue
        alvo = f"{emissor}_{cat}"
        if alvo in categorias:
            saida[alvo] = [*saida.get(alvo, []), *itens]
            del saida[cat]
    return saida


def _rotulo_de(cat: str) -> str:
    """'rinno_filmes' -> 'Filmes'; 'tecnologia' -> 'Tecnologia'."""
    nome = cat
    for emissor in EMISSORES:
        if nome.startswith(f"{emissor}_"):
            nome = nome[len(emissor) + 1:]
    return nome.replace("_", " ").strip().capitalize()


def _acrescentar_fora_da_tabela(orc: Orcamento, fora: dict[str, list]) -> None:
    """Categorias que a tabela não tem entram no orçamento com os itens que a
    pessoa pediu: preço informado, ou zero (a pendência pede o valor)."""
    for cat, itens in fora.items():
        bloco = orc.categorias.setdefault(cat, CategoriaOrcada(nome=cat, rotulo=_rotulo_de(cat)))
        for entrada in itens:
            desc, informado = entrada_de_item(entrada)
            if not desc:
                continue
            bloco.itens.append(ItemOrcado(
                descricao=desc,
                descricao_normalizada=desc[:1].upper() + desc[1:],
                preco=informado if informado is not None else 0,
                fonte="informado" if informado is not None else "sem_tabela",
            ))


def _inteiro_ou_none(valor: Any) -> int | None:
    try:
        return int(round(float(valor))) if valor not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None


def levantar(conn: psycopg.Connection, estrutura: dict[str, Any]) -> dict[str, Any]:
    """Resolve estratégia e preços (NEON) e devolve o orçamento fechado."""
    avisos = list(estrutura.get("_avisos", []))

    emissor = empresa_emissora(estrutura.get("emissor")).chave
    tabela_precos = resolver_tabela(emissor, estrutura.get("tabela_precos"))

    tabela: TabelaPrecos = carregar_tabela_precos(conn, tabela_precos)
    if not tabela.categorias():
        # Aconteceu em produção: o backend subiu sem o seed e a Rinno saiu
        # zerada. A tabela é base, não verdade absoluta: sem ela os itens
        # entram do mesmo jeito, com o preço que a pessoa informar — e o aviso
        # diz o que falta no banco.
        avisos.append(
            f"O catálogo da {empresa_emissora(emissor).nome} não está carregado no banco "
            f"(tabela '{tabela_precos}' vazia) — informe os preços à mão ou rode "
            "`python -m scripts.seed_precos` com o DATABASE_URL de produção."
        )
    estrutura = no_namespace_do_emissor(estrutura, emissor, tabela.categorias())
    descricoes = _descricoes(estrutura, tabela.categorias())

    ajuste_pct = float(estrutura.get("ajuste_planilha_pct") or 0)
    preco_por_imagem = _inteiro_ou_none(estrutura.get("preco_por_imagem"))
    ambientes = _inteiro_ou_none(estrutura.get("ambientes"))
    if ambientes is not None and ambientes < 1:
        raise ValueError(f"ambientes inválido: {ambientes} (deve ser >= 1)")
    if preco_por_imagem is not None and preco_por_imagem < 0:
        raise ValueError(f"preco_por_imagem inválido: {preco_por_imagem} (deve ser >= 0)")
    if not -100 < ajuste_pct < 1000:
        raise ValueError(f"ajuste_planilha_pct inválido: {ajuste_pct}")
    # Itens de categorias fora da tabela escolhida (tecnologia no mcmv, ou
    # qualquer coisa quando a tabela está vazia) entram mesmo assim: com o
    # preço informado, ou zerados e com pendência para a pessoa preencher. A
    # tabela sugere preço; não decide o que pode estar na proposta.
    fora_da_tabela = {
        cat: itens for cat, itens in estrutura.items()
        if cat not in tabela.categorias() and isinstance(itens, list) and itens
        and not cat.startswith("_")
    }
    for cat, itens in fora_da_tabela.items():
        avisos.append(
            f"Categoria '{cat}' não está na tabela {tabela_precos} — "
            f"{len(itens)} item(ns) sem preço de tabela; informe o valor."
        )
    # Tour virtual é cobrado por ambiente: 7 áreas de lazer custam 7x cada
    # etapa. Sem a quantidade, a conta sai por 1 e o valor fica errado — por
    # isso o aviso, e a pendência em `_pendencias` quando ninguém perguntou.
    for cat in tabela.categorias():
        if e_categoria_por_ambiente(cat) and descricoes.get(cat):
            avisos.append(
                f"{tabela.meta(cat)['rotulo']} é cobrado por ambiente — a conta está "
                f"com {ambientes or 1} ambiente(s). Confirme quantas áreas o "
                "empreendimento tem."
            )

    cliente = estrutura["cliente"]["empresa"]
    pedida = estrutura.get("estrategia", "auto")

    historico = Historico(conn)
    orc = None
    if pedida == "historico" or (pedida == "auto" and historico.tem_cliente(cliente)):
        orc = orcar_pelo_historico(historico, cliente, descricoes, tabela,
                                   preco_por_imagem=preco_por_imagem)
        if orc is None and pedida == "historico":
            avisos.append(f"Cliente '{cliente}' não tem histórico — usei a tabela de planilha.")
    if orc is None:
        orc = orcar_pela_planilha(descricoes, tabela, ajuste_pct=ajuste_pct,
                                  preco_por_imagem=preco_por_imagem,
                                  ambientes=ambientes or 1)
    orc.ambientes = max(1, ambientes or 1)
    _acrescentar_fora_da_tabela(orc, fora_da_tabela)

    desconto = None
    if estrutura.get("desconto_pct", 0):
        desconto = Desconto(
            tipo="percentual",
            valor=float(estrutura["desconto_pct"]),
            rotulo=estrutura.get("desconto_label") or "",
        )

    return {
        "cliente": estrutura["cliente"],
        # A estrutura já no namespace do emissor: quem devolve ao front tem de
        # usar esta, senão o preview lista `rinno_filmes` sem achar os itens.
        "estrutura": estrutura,
        "fechado": fechar_orcamento(orc, desconto),
        "estrategia_usada": orc.estrategia,
        "emissor": emissor,
        "tabela_precos": tabela_precos,
        "avisos": avisos,
    }


def gerar(conn: psycopg.Connection, estrutura: dict[str, Any], dir_saida: Path) -> dict[str, Any]:
    """Levanta, persiste no NEON, gera o .docx e tenta subir no R2."""
    lev = levantar(conn, estrutura)
    cliente = lev["cliente"]
    fechado = lev["fechado"]

    cliente_id = upsert_cliente(conn, cliente["empresa"], cliente.get("contato"))
    proposta_id = salvar_proposta(
        conn, cliente_id, fechado, referencia=cliente.get("ref"),
        tabela_precos=lev["tabela_precos"], emissor=lev["emissor"],
    )

    docx_path = Path(dir_saida) / f"proposta_{proposta_id}.docx"
    gerar_docx(
        cliente,
        fechado,
        docx_path,
        emissor=lev["emissor"],
        mostra_precos_individuais=bool(estrutura.get("mostrar_precos_individuais")),
    )

    # Emissor no caminho: o mesmo cliente/ref pode ter proposta das três
    # empresas, e no R2 elas ficam separadas por pasta.
    chave = (f"Propostas/{lev['emissor']}/{_slug(cliente['empresa'])}"
             f"/{_slug(cliente.get('ref') or 'geral')}/proposta_{proposta_id}.docx")
    docx_url = enviar_docx(docx_path, chave)
    if docx_url:
        atualizar_docx_url(conn, proposta_id, docx_url)
    else:
        lev["avisos"].append("Upload no R2 indisponível — use o download direto da API.")

    # Os SELECTs de levantar abrem transação implícita na conexão, o que rebaixa
    # os conn.transaction() dos repositórios a SAVEPOINTs — sem este commit, o
    # close() da conexão descartaria a proposta inteira.
    conn.commit()

    return {
        "proposta_id": proposta_id,
        "docx_path": str(docx_path),
        "docx_url": docx_url,
        "chave_r2": chave,
        "fechado": fechado,
        "emissor": lev["emissor"],
        "avisos": lev["avisos"],
    }
