"""Carrega a tabela de preços e classifica descrições livres de itens.

Você passa a descrição de uma imagem (ex.: "Fachada vista da calçada") e a
categoria geral ("externas"/"internas"/"plantas"); a função descobre qual
linha da tabela aplicar via regex e devolve chave, descrição padrão e preço.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.dominio.texto import normalizar

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"
PRECOS_PATH = DADOS_DIR / "precos_planilha.json"

CATEGORIAS_VALIDAS = ("externas", "internas", "plantas")


class TabelaPrecos:
    """Wrapper sobre o JSON da planilha com helper de classificação."""

    def __init__(self, dados: dict[str, Any] | None = None) -> None:
        if dados is None:
            with open(PRECOS_PATH, encoding="utf-8") as f:
                dados = json.load(f)
        self.dados = dados

    def classificar(self, descricao: str, categoria: str) -> dict[str, Any]:
        if categoria not in CATEGORIAS_VALIDAS:
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
