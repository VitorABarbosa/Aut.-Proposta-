"""Carrega a tabela de preços e classifica descrições livres de itens.

Você passa a descrição de uma imagem (ex.: "Fachada vista da calçada") e a
categoria geral (ex.: "externas"/"internas"/"plantas"/"filmes"/"tecnologia");
a função descobre qual linha da tabela aplicar via regex e devolve chave,
descrição padrão e preço. As categorias válidas são as que existirem em
`self.dados` — dinâmicas, vindas do catálogo (NEON em produção; o JSON
`precos_2026.json` quando não há conexão).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.dominio.texto import normalizar

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"
PRECOS_PATH = DADOS_DIR / "precos_2026.json"


def _dados_da_tabela(catalogo: dict[str, Any], tabela: str = "padrao") -> dict[str, Any]:
    """Converte o shape do catálogo versionado (precos_2026.json) para o
    shape interno de `TabelaPrecos.dados`."""
    dados: dict[str, Any] = {}
    for cat in catalogo[tabela]["categorias"]:
        dados[cat["nome"]] = {
            "_default": cat["default"],
            "_descricao_padrao": cat["descricao_padrao"],
            "_ordem": cat["ordem"],
            "_rotulo": cat["rotulo"],
            "_prefixo": cat["prefixo"],
            "tabela": cat["itens"],
        }
    return dados


class TabelaPrecos:
    """Wrapper sobre os dados de preços com helpers de classificação."""

    def __init__(self, dados: dict[str, Any] | None = None) -> None:
        if dados is None:
            with open(PRECOS_PATH, encoding="utf-8") as f:
                catalogo = json.load(f)
            dados = _dados_da_tabela(catalogo, "padrao")
        self.dados = dados

    def categorias(self) -> list[str]:
        """Nomes das categorias presentes, ordenados por `_ordem`."""
        return sorted(self.dados.keys(), key=lambda c: self.dados[c].get("_ordem", 0))

    def meta(self, categoria: str) -> dict[str, Any]:
        """Metadados de catálogo da categoria: rótulo (docx), prefixo e ordem."""
        bloco = self.dados[categoria]
        return {
            "rotulo": bloco.get("_rotulo", ""),
            "prefixo": bloco.get("_prefixo", ""),
            "ordem": bloco.get("_ordem", 0),
        }

    def classificar(self, descricao: str, categoria: str) -> dict[str, Any]:
        if categoria not in self.dados:
            raise ValueError(f"Categoria inválida: {categoria}")

        bloco = self.dados[categoria]
        alvo = normalizar(descricao)

        for linha in bloco["tabela"]:
            for padrao in linha["padroes"]:
                if re.search(padrao, alvo):
                    return {
                        "chave": linha["chave"],
                        "descricao_padrao": linha["descricao"],
                        "preco": linha["preco"],
                    }

        return {
            "chave": "default",
            "descricao_padrao": bloco["_descricao_padrao"],
            "preco": bloco["_default"],
        }
