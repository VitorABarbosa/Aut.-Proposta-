"""Roda os casos-ouro contra o modelo de verdade e dá a nota.

Cada caso em `tests/ia/casos/*.json` é uma conversa real (ou tirada de uma
proposta real) e o que a ÚLTIMA chamada de precificação precisa conter. O
script manda os turnos do usuário para `responder`, um a um, e confere a
chamada que a IA fez — ferramenta certa, categorias certas, preços ditos pelo
usuário, sem perguntas que não deveria fazer.

Uso (precisa da IA e do catálogo no banco):

    DATABASE_URL=... OPENAI_API_KEY=... python -m scripts.avaliar_chat
    OPENAI_MODEL=gpt-4.1 python -m scripts.avaliar_chat        # compara modelos
    python -m scripts.avaliar_chat archtech_viral_4k           # um caso só

Sem isso, toda mudança de prompt ou de modelo é palpite. Com isso, é número.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from app.dominio.orcamento import entrada_de_item
from app.dominio.texto import normalizar

CASOS_DIR = Path(__file__).resolve().parent.parent / "tests" / "ia" / "casos"


def carregar_casos(filtro: str | None = None) -> dict[str, dict]:
    casos = {}
    for arquivo in sorted(CASOS_DIR.glob("*.json")):
        if filtro and filtro not in arquivo.stem:
            continue
        casos[arquivo.stem] = json.loads(arquivo.read_text(encoding="utf-8"))
    return casos


def _bate(padrao: str, texto: str) -> bool:
    """`contem` aceita alternativas com "|" e ignora acento/caixa."""
    return any(normalizar(alt) in normalizar(texto) for alt in padrao.split("|"))


def verificar(esperado: dict, nome: str | None, estrutura: dict | None,
              respostas: list[str]) -> list[str]:
    """Compara a chamada feita com o esperado. Lista vazia = passou."""
    falhas: list[str] = []
    if nome is None or estrutura is None:
        return [f"nenhuma chamada de precificação; a IA respondeu: {respostas[-1][:120]!r}"
                if respostas else "nenhuma chamada de precificação"]

    if esperado.get("ferramenta") and nome != esperado["ferramenta"]:
        falhas.append(f"ferramenta: esperava {esperado['ferramenta']}, chamou {nome}")

    cliente = estrutura.get("cliente") or {}
    if isinstance(cliente, str):
        cliente = {"empresa": cliente}
    for campo, valor in (esperado.get("cliente") or {}).items():
        if not _bate(valor, str(cliente.get(campo) or "")):
            falhas.append(f"cliente.{campo}: esperava conter {valor!r}, veio {cliente.get(campo)!r}")

    entradas: dict[str, list[tuple[str, int | None]]] = {}
    for cat, itens in estrutura.items():
        if isinstance(itens, list) and not cat.startswith("_"):
            entradas[cat] = [entrada_de_item(e) for e in itens if e not in (None, "")]

    for cat, specs in (esperado.get("categorias") or {}).items():
        disponiveis = list(entradas.get(cat, []))
        if not disponiveis:
            falhas.append(f"categoria {cat}: esperava itens, veio vazia (tem: "
                          f"{[c for c, v in entradas.items() if v]})")
            continue
        for spec in specs:
            achado = None
            for i, (desc, preco) in enumerate(disponiveis):
                if _bate(spec["contem"], desc):
                    achado = i
                    break
            if achado is None:
                falhas.append(f"{cat}: nenhum item contendo {spec['contem']!r} "
                              f"(itens: {[d for d, _ in disponiveis]})")
                continue
            desc, preco = disponiveis.pop(achado)
            if "descricao_contem" in spec and not _bate(spec["descricao_contem"], desc):
                falhas.append(f"{cat}: {desc!r} deveria conter {spec['descricao_contem']!r}")
            if "preco" in spec and preco != spec["preco"]:
                falhas.append(f"{cat}: {desc!r} deveria ter preco={spec['preco']}, veio {preco}")

    for cat in esperado.get("sem_categorias") or []:
        if entradas.get(cat):
            falhas.append(f"categoria {cat} não deveria ter itens (veio {entradas[cat]})")

    for campo in ("preco_por_imagem", "ajuste_planilha_pct", "desconto_pct"):
        if campo in esperado:
            veio = estrutura.get(campo)
            veio_num = float(veio) if veio not in (None, "") else 0.0
            if veio_num != float(esperado[campo]):
                falhas.append(f"{campo}: esperava {esperado[campo]}, veio {veio}")

    total = sum(len(v) for v in entradas.values())
    if "quantidade_total" in esperado and total != esperado["quantidade_total"]:
        falhas.append(f"quantidade de itens: esperava {esperado['quantidade_total']}, veio {total}")
    if "quantidade_minima" in esperado and total < esperado["quantidade_minima"]:
        falhas.append(f"quantidade de itens: esperava ao menos {esperado['quantidade_minima']}, veio {total}")

    for frase in esperado.get("nao_perguntar") or []:
        if any(_bate(frase, r) for r in respostas):
            falhas.append(f"a IA perguntou {frase!r}, e não devia")
    return falhas


def ultima_precificacao(traco: list[dict]) -> tuple[str | None, dict | None]:
    for chamada in reversed(traco):
        nome = chamada.get("nome", "")
        if nome.startswith("precificar_"):
            return nome, (chamada.get("args") or {}).get("estrutura")
    return None, None


def rodar_caso(conn, caso: dict) -> tuple[list[str], list[dict], list[str]]:
    from app.ia.chat import responder

    mensagens: list[dict] = []
    traco: list[dict] = []
    respostas: list[str] = []
    for turno in caso["turnos"]:
        mensagens.append({"role": "user", "content": turno})
        resposta = responder(conn, mensagens, traco=traco)
        respostas.append(resposta["mensagem"])
        mensagens.append({"role": "assistant", "content": resposta["mensagem"]})
    nome, estrutura = ultima_precificacao(traco)
    return verificar(caso["esperado"], nome, estrutura, respostas), traco, respostas


def main(argv: list[str]) -> int:
    import os

    from app.db.conexao import get_conn

    filtro = argv[0] if argv else None
    casos = carregar_casos(filtro)
    if not casos:
        print(f"nenhum caso em {CASOS_DIR}" + (f" com '{filtro}'" if filtro else ""))
        return 2
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY não definido — a avaliação precisa da IA de verdade.")
        return 2

    modelo = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"modelo: {modelo}  ·  {len(casos)} caso(s)\n")
    aprovados = 0
    inicio = time.monotonic()
    for nome, caso in casos.items():
        conn = get_conn()
        try:
            falhas, traco, respostas = rodar_caso(conn, caso)
        finally:
            conn.close()
        ok = not falhas
        aprovados += ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {nome}")
        for f in falhas:
            print(f"        - {f}")
        if not ok and respostas:
            print(f"        IA: {respostas[-1][:200]!r}")
    print(f"\n{aprovados}/{len(casos)} aprovados  ·  {time.monotonic() - inicio:.0f}s  ·  {modelo}")
    return 0 if aprovados == len(casos) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
