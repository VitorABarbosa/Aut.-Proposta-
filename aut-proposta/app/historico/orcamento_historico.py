"""2º levantamento: reaplica os preços que o cliente pagou no último projeto.

Ordem de resolução de preço por item: item exato no histórico → item similar
(substring) → média da categoria do cliente → preço de planilha (fallback).
As categorias percorridas são as da tabela de preços atual (dinâmicas).
"""
from __future__ import annotations

from app.dominio.orcamento import (
    CategoriaOrcada,
    ItemOrcado,
    Orcamento,
    _formata_descricao,
)
from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar
from app.historico.historico import Historico


def orcar_pelo_historico(
    historico: Historico,
    cliente: str,
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos,
) -> Orcamento | None:
    if not historico.tem_cliente(cliente):
        return None

    tab_cliente = historico.tabela_precos_inferida(cliente) or {}
    medias = historico.medias_por_categoria(cliente) or {}

    cats: dict[str, CategoriaOrcada] = {
        c: CategoriaOrcada(nome=c, rotulo=tabela.meta(c)["rotulo"]) for c in tabela.categorias()
    }

    for cat in tabela.categorias():
        for desc in descricoes.get(cat, []):
            chave = normalizar(desc)
            preco: int | None = None
            fonte = ""

            if chave in tab_cliente.get(cat, {}):
                preco = tab_cliente[cat][chave]
                fonte = f"historico:{cliente}:item_exato"

            if preco is None:
                for k_hist, v_hist in tab_cliente.get(cat, {}).items():
                    if chave in k_hist or k_hist in chave:
                        preco = v_hist
                        fonte = f"historico:{cliente}:item_similar"
                        break

            if preco is None and cat in medias:
                preco = int(round(medias[cat]))
                fonte = f"historico:{cliente}:media_categoria"

            if preco is None:
                classif = tabela.classificar(desc, cat)
                preco = classif["preco"]
                fonte = f"fallback_planilha:{classif['chave']}"

            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=_formata_descricao(desc, cat, tabela),
                    preco=preco,
                    fonte=fonte,
                )
            )

    return Orcamento(estrategia=f"historico:{cliente}", categorias=cats)
