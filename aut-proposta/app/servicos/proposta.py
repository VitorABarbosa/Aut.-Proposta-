"""Orquestração de uma proposta: NEON -> orçamento -> .docx -> R2 -> NEON.

Único lugar que decide a estratégia (planilha × histórico) e o único caminho
de produção que monta TabelaPrecos — sempre via carregar_tabela_precos(conn).
"""
from __future__ import annotations

import re
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
    e_categoria_de_imagem,
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
    from app.ia.parser import catalogo_para_prompt, parse

    emp = empresa_emissora(emissor)
    tabela = carregar_tabela_precos(conn, emp.tabela_padrao)
    estrutura = parse(texto, categorias=tabela.categorias(),
                      catalogo=catalogo_para_prompt(tabela))
    estrutura["emissor"] = emp.chave
    estrutura["tabela_precos"] = emp.tabela_padrao
    return estrutura


def _slug(texto: str) -> str:
    """Normaliza e converte espaços em hífens para slug de chave R2."""
    return normalizar(texto).replace(" ", "-")


def _descricoes(estrutura: dict[str, Any], categorias: list[str]) -> dict[str, list[str]]:
    return {cat: estrutura.get(cat, []) for cat in categorias}


# Serviço com nome próprio -> categoria a que ele pertence, aconteça o que
# acontecer com o palpite do modelo.
#
# A IA insiste em jogar serviço dentro de ilustrações: a maquete eletrônica já
# saiu três vezes como "Perspectiva Maquete eletrônica" a R$ 1.900, que é o
# preço de uma cena qualquer. Prompt não segurou, então a regra é de código.
# Ilustração externa/interna é CENA do empreendimento ("fachada noturna",
# "piscina"); nome de serviço nunca é cena.
#
# A ordem importa: o padrão mais específico ganha, e por isso "aplicação web"
# vem antes de qualquer coisa que case com "web".
SERVICO_POR_PADRAO: tuple[tuple[str, str], ...] = (
    (r"aplica[cç][aã]o\s*web|aplicativo\s*web|tela\s*touch|touch\s*screen", "tecnologia"),
    (r"explorador|d\.?\s?brave", "tecnologia"),
    (r"maquete", "tecnologia"),
    (r"tour\s*virtual|vista\s*virtual|vr\s*360|360\s*vr|panos?\s*360", "tour_virtual"),
    # A Flying não faz filme — filme e take são da Rinno, sempre.
    (r"\bfilmes?\b|document[aá]rio", "rinno_filmes"),
    (r"\btakes?\b", "rinno_takes"),
    (r"stand\s*de\s*vendas|\bpdv\b|apto\s*modelo|apartamento\s*modelo", "nid_interiores"),
    (r"projeto\s*executivo|arquitet[oô]nico|paisagismo", "nid_arquitetura"),
    # "Estudo de fachada" e "cromático" são o nome antigo do design de fachada,
    # que é serviço da NID — nunca da Flying, onde já esteve no catálogo.
    (r"design\s*de\s*fachada|estudo\s*(de)?\s*fachada|crom[aá]tico", "nid_fachada"),
)


# Categoria que existiu e não existe mais, e para onde o que chega nela vai.
# O modelo aprendeu com conversas antigas e continua mandando estas chaves.
CATEGORIAS_APOSENTADAS = {
    # "drone e fotografia aérea" a casa chama de fotomontagem ou voo de
    # pássaro, que são ilustrações externas.
    "drone": "externas",
    # Filme é da Rinno; a Flying nunca fez.
    "filmes": "rinno_filmes",
    "takes": "rinno_takes",
    # "Estudo de fachada" virou design de fachada, da NID.
    "estudos": "nid_fachada",
}


def sem_categorias_aposentadas(estrutura: dict[str, Any]) -> dict[str, Any]:
    """Move o que chegou numa categoria que saiu do catálogo para a de hoje."""
    saida = dict(estrutura)
    for velha, nova in CATEGORIAS_APOSENTADAS.items():
        itens = saida.pop(velha, None)
        if isinstance(itens, list) and itens:
            saida[nova] = [*saida.get(nova, []), *itens]
    return saida


def servicos_fora_das_imagens(estrutura: dict[str, Any], tabela: TabelaPrecos) -> dict[str, Any]:
    """Tira de ilustrações os itens que são serviço, e põe na categoria deles.

    Roda ANTES do namespace do emissor, para que um filme mandado como
    `filmes` numa proposta da Rinno ainda vire `rinno_filmes` depois.

    Serviço cuja categoria não existe na tabela carregada sai das imagens do
    mesmo jeito: vai para a categoria certa e cai em "fora da tabela", que
    pede o preço. Melhor sem preço do que cobrado como se fosse uma cena.
    """
    saida = dict(estrutura)
    for cat in list(estrutura):
        if not isinstance(estrutura[cat], list) or not _e_de_imagem(cat, tabela):
            continue
        ficam, movidos = [], []
        for entrada in estrutura[cat]:
            desc, _ = entrada_de_item(entrada)
            alvo = _categoria_de_servico(desc)
            if alvo is None or alvo == cat:
                ficam.append(entrada)
            else:
                movidos.append((alvo, entrada))
        if not movidos:
            continue
        saida[cat] = ficam
        for alvo, entrada in movidos:
            saida[alvo] = [*saida.get(alvo, []), entrada]
    return saida


# Nomes das categorias de imagem do grupo. A tabela carregada resolve o caso
# normal (categoria com prefixo de escrita), mas a proposta da Rinno não tem
# `externas` na tabela dela — e é justamente ali que o modelo larga um filme.
NOMES_DE_IMAGEM = ("externas", "internas", "plantas")


def _e_de_imagem(cat: str, tabela: TabelaPrecos) -> bool:
    if cat.startswith("_") or cat == "cliente":
        return False
    if cat in tabela.categorias():
        return e_categoria_de_imagem(cat, tabela)
    nome = cat
    for emissor in EMISSORES:
        if nome.startswith(f"{emissor}_"):
            nome = nome[len(emissor) + 1:]
    return nome in NOMES_DE_IMAGEM


def _categoria_de_servico(descricao: str) -> str | None:
    alvo = normalizar(descricao)
    for padrao, categoria in SERVICO_POR_PADRAO:
        if re.search(padrao, alvo):
            return categoria
    return None


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


def _empresa_da_categoria(cat: str) -> str | None:
    """'nid_fachada' -> 'nid'. Categoria sem prefixo é da Flying, que não usa um."""
    for emissor in EMISSORES:
        if cat.startswith(f"{emissor}_"):
            return emissor
    return None


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
    estrutura = sem_categorias_aposentadas(estrutura)
    estrutura = servicos_fora_das_imagens(estrutura, tabela)
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
        dona = _empresa_da_categoria(cat)
        if dona and dona != emissor:
            # Serviço de outra empresa do grupo: dizer de quem é poupa a
            # descoberta. Cada proposta é de uma empresa só — "design de
            # fachada" numa proposta da Flying é proposta da NID.
            avisos.append(
                f"'{_rotulo_de(cat)}' é serviço da {empresa_emissora(dona).nome}, não da "
                f"{empresa_emissora(emissor).nome} — refaça por lá, ou informe o valor à "
                f"mão ({len(itens)} item(ns) sem preço)."
            )
        else:
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
    sem_preco: list[str] = []

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
    orc.parcelas = _inteiro_ou_none(estrutura.get("parcelas"))
    if orc.parcelas is not None and not 1 <= orc.parcelas <= 24:
        raise ValueError(f"parcelas inválido: {orc.parcelas} (use de 1 a 24)")
    orc.mostrar_ambientes = estrutura.get("mostrar_ambientes", True) is not False
    _acrescentar_fora_da_tabela(orc, fora_da_tabela)

    # Serviço sem preço não trava a proposta: entra com zero e o aviso lembra
    # de pôr o valor à mão. Era pendência, e pendência impede de gerar.
    sem_preco = [i.descricao_normalizada for cat in orc.categorias.values()
                 for i in cat.itens
                 if i.preco == 0 and i.fonte.startswith(("a_definir", "sem_tabela"))]
    if sem_preco:
        avisos.append(
            f"Sem preço de tabela ({len(sem_preco)}): {', '.join(sem_preco[:4])}"
            f"{'…' if len(sem_preco) > 4 else ''}. Clique no preço de cada um no "
            "preview para informar o valor — dá para gerar assim mesmo."
        )

    # Valor fechado da proposta: "fechamos por 100 mil". A tabela é base, e o
    # número que o cliente vê é o que foi negociado — então o total pode ser
    # escrito à mão, e o desconto vira a diferença em reais (o domínio já sabia
    # fazer isso; faltava alguém pedir).
    #
    # Fechar o total manda no desconto percentual: quem digita o valor final
    # está dizendo o que quer ver na proposta.
    total_fechado = _inteiro_ou_none(estrutura.get("total_fechado"))
    rotulo = estrutura.get("desconto_label") or ""
    desconto = None
    acima_da_soma = False
    if total_fechado is not None:
        subtotal = orc.subtotal
        if total_fechado > subtotal:
            # Fechar acima da soma é negociação legítima, não erro: o número que
            # o cliente lê é o negociado. Antes isto levantava ValueError, e a
            # IA, ao receber o erro, refazia a chamada com a estrutura
            # mutilada — foi assim que a proposta da Tavares e Rosseti perdeu
            # as 30 imagens e o tour. Vale o número, com aviso.
            acima_da_soma = True
        else:
            desconto = Desconto(tipo="valor", valor=float(subtotal - total_fechado),
                                rotulo=rotulo)
    elif estrutura.get("desconto_pct", 0):
        desconto = Desconto(
            tipo="percentual",
            valor=float(estrutura["desconto_pct"]),
            rotulo=rotulo,
        )

    # A estrutura devolvida (e gravada) carrega o que foi RESOLVIDO aqui: sem
    # isso, reabrir a proposta para editar perde o emissor e a tabela.
    estrutura["emissor"] = emissor
    estrutura["tabela_precos"] = tabela_precos

    return {
        "cliente": estrutura["cliente"],
        # A estrutura já no namespace do emissor: quem devolve ao front tem de
        # usar esta, senão o preview lista `rinno_filmes` sem achar os itens.
        "estrutura": estrutura,
        "fechado": _fechar(orc, desconto, total_fechado if acima_da_soma else None, avisos),
        "estrategia_usada": orc.estrategia,
        "emissor": emissor,
        "tabela_precos": tabela_precos,
        "avisos": avisos,
    }


def _fechar(orc: Orcamento, desconto: "Desconto | None", total_acima: int | None,
            avisos: list[str]) -> dict[str, Any]:
    """Fecha o orçamento, respeitando um total negociado acima da soma dos itens.

    Sem desconto a mostrar, a proposta sai com o valor fechado limpo — que é
    como ela já imprime qualquer total sem desconto.
    """
    fechado = fechar_orcamento(orc, desconto)
    if total_acima is not None:
        avisos.append(
            f"O valor fechado (R$ {total_acima:,}) está acima da soma dos itens "
            f"(R$ {orc.subtotal:,}) — vale o valor fechado.".replace(",", ".")
        )
        fechado["financeiro"] = {**fechado["financeiro"], "total": float(total_acima),
                                 "desconto_pct": 0.0, "desconto_valor": 0.0}
    return fechado


def gerar(conn: psycopg.Connection, estrutura: dict[str, Any], dir_saida: Path) -> dict[str, Any]:
    """Levanta, persiste no NEON, gera o .docx e tenta subir no R2."""
    lev = levantar(conn, estrutura)
    cliente = lev["cliente"]
    fechado = lev["fechado"]

    cliente_id = upsert_cliente(conn, cliente["empresa"], cliente.get("contato"))
    proposta_id = salvar_proposta(
        conn, cliente_id, fechado, referencia=cliente.get("ref"),
        tabela_precos=lev["tabela_precos"], emissor=lev["emissor"],
        estrutura=lev["estrutura"],
    )

    docx_path = Path(dir_saida) / f"proposta_{proposta_id}.docx"
    gerar_docx(cliente, fechado, docx_path, emissor=lev["emissor"])

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
