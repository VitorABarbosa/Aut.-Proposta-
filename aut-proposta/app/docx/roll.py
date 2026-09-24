"""O .docx do roll: a lista do que entra em produção, sem um preço sequer.

Os rolls reais são curtos e sempre iguais — cabeçalho com CLIENTE - REF,
seções numeradas (2.1 Ilustrações Externas, 2.2 Internas, 2.3 Plantas Baixas),
os serviços com o escopo embaixo, e a data de aprovação no pé:

    OUSY - REF: VILA MARIANA

    2.1 – Ilustrações Externas
    1.  Fachada noturna conceitual
    ...
    2.4. Desenvolvimento Aplicação Web – Para Tela Touch
    1. Catálogo Digital Interativo …

    Aprovado em: 30 de junho de 2026.

Vai no timbrado da empresa que produz, como a proposta — por isso reusa o
`abrir_documento` e a tipografia de `base.py`.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from app.docx.base import _par, _run, _subtitulo, abrir_documento
from app.docx.flying import _escopo_de
from app.docx.formatos import data_extenso
from app.dominio.roll import ROTULO, numerar
from app.empresas import Empresa, empresa


def _cabecalho(doc, cliente: dict[str, str]) -> None:
    ref = (cliente.get("ref") or "").upper()
    p = _par(doc, depois=12)
    _run(p, f"{(cliente.get('empresa') or '').upper()} - REF: {ref}" if ref
            else (cliente.get("empresa") or "").upper(), estilo="b")


def _titulo_do_bloco(bloco: dict[str, Any]) -> str:
    """O nome da seção. Imagem tem rótulo fixo; serviço tem nome próprio."""
    if bloco.get("titulo"):
        return bloco["titulo"]
    return ROTULO.get(bloco.get("tipo") or "", "Itens")


def itens_do_bloco(bloco: dict[str, Any]) -> list[str]:
    """O que sai listado embaixo do título.

    No roll o escopo do serviço É a lista numerada ("1. Catálogo Digital
    Interativo, 2. Apresentação do Empreendimento…"), não um sub-nível. Então
    serviço conhecido que chega sem itens ganha o escopo que já está
    cadastrado no gerador da proposta — a mesma lista, escrita uma vez só.
    """
    itens = list(bloco.get("itens") or [])
    if itens or bloco.get("tipo") != "servico":
        return itens
    return _escopo_de(bloco.get("titulo") or "")


def escrever(doc, empresa_: Empresa, cliente: dict[str, str],
             roll: dict[str, Any], data: dt.date) -> None:
    _cabecalho(doc, cliente)
    for numero, bloco in numerar(roll.get("blocos") or []):
        titulo = _titulo_do_bloco(bloco)
        _subtitulo(doc, f"{numero} – {titulo}")
        for idx, item in enumerate(itens_do_bloco(bloco), start=1):
            p = _par(doc, depois=2, recuo=1.25)
            _run(p, f"{idx}. {item}")

    aprovado = roll.get("aprovado_em")
    quando = dt.date.fromisoformat(aprovado) if isinstance(aprovado, str) and aprovado else data
    p = _par(doc, antes=18, depois=6)
    _run(p, f"Aprovado em: {data_extenso(quando)}.")


def gerar_roll_docx(cliente: dict[str, str], roll: dict[str, Any], saida: Path,
                    data: dt.date | None = None, emissor: str | None = None) -> Path:
    """Escreve o roll da empresa `emissor` (default: Flying) em `saida`."""
    emp = empresa(emissor)
    doc = abrir_documento(emp)
    escrever(doc, emp, cliente, roll, data or dt.date.today())
    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida
