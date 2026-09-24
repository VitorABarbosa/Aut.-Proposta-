"""Como o arquivo da proposta se chama quando chega na mão do cliente.

O padrão do grupo é

    Flying_Factus_Upside_Vista_AnexoI_R00

ou seja: quem emite, quem recebe, qual empreendimento, qual serviço, o anexo
e a revisão. `proposta_57.docx` é o nome interno — serve para o disco e para
não colidir no R2 —, mas ninguém manda `proposta_57.docx` para uma
incorporadora.

O serviço é um palpite bem-informado (a categoria que pesa mais no
orçamento), não um oráculo: o nome inteiro é editável no preview, e o que a
pessoa escrever lá manda.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

ANEXO = "AnexoI"

# Nome curto de cada emissor no arquivo.
EMISSOR_NO_ARQUIVO = {"flying": "Flying", "rinno": "Rinno", "nid": "NID"}

# Categoria -> palavra do serviço no nome do arquivo. Duas categorias de
# imagem dão a mesma palavra de propósito: "Imagens" é como a proposta é
# chamada internamente, não "Externas_Internas".
SERVICO_NO_ARQUIVO = {
    "externas": "Imagens",
    "internas": "Imagens",
    "plantas": "Plantas",
    "tour_virtual": "Vista",
    "tecnologia": "Tecnologia",
    "rinno_filmes": "Filmes",
    "rinno_takes": "Takes",
    "rinno_pacotes": "Filmes",
    "nid_fachada": "Fachada",
    "nid_interiores": "Interiores",
    "nid_pdv": "PDV",
    "nid_produto": "Produto",
    "nid_arquitetura": "Arquitetura",
    "nid_decoracao": "Decoracao",
}

# Dentro de "tecnologia" o serviço tem nome próprio, e é ele que vai no
# arquivo — foi assim nas propostas que já saíram (Flying_D.sbrave_Elecon).
SERVICO_POR_ITEM = (
    (re.compile(r"d\.? ?sbrave", re.I), "D.sbrave"),
    (re.compile(r"maquete", re.I), "Maquete"),
    (re.compile(r"aplica[çc][ãa]o|app|web ?touch", re.I), "App"),
)


def _token(texto: str) -> str:
    """Um pedaço do nome: sem acento, sem espaço, sem separador solto.

    Mantém o ponto ("D.sbrave") e junta as palavras em CamelCase ("Casa
    Viva" -> "CasaViva"), porque o `_` já é o separador dos pedaços.
    """
    limpo = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")
    palavras = re.findall(r"[A-Za-z0-9.]+", limpo)
    return "".join(p[:1].upper() + p[1:] for p in palavras)


def _servico(orcamento: dict[str, Any]) -> str:
    """A palavra do serviço: a categoria que pesa mais no orçamento.

    Proposta com imagens e tour junto tem um nome só, e quem manda é o que
    foi contratado de maior — se estiver errado, troca no preview.
    """
    categorias = [
        (nome, bloco) for nome, bloco in orcamento.items()
        if not nome.startswith("_") and isinstance(bloco, dict) and bloco.get("itens")
    ]
    if not categorias:
        return ""
    nome, bloco = max(categorias, key=lambda cb: (cb[1].get("total") or 0, cb[1].get("qtd") or 0))
    for item in bloco["itens"]:
        for padrao, palavra in SERVICO_POR_ITEM:
            if padrao.search(item.get("descricao", "")):
                return palavra
    return SERVICO_NO_ARQUIVO.get(nome, _token(nome))


def nome_do_arquivo(emissor: str, cliente: str, referencia: str | None,
                    orcamento: dict[str, Any], revisao: int = 0) -> str:
    """Emissor_Cliente_Empreendimento_Serviço_AnexoI_Rnn, sem extensão.

    Pedaço vazio some em vez de virar `__`: cliente sem empreendimento sai
    `Flying_Factus_Vista_AnexoI_R00`.
    """
    pedacos = [
        EMISSOR_NO_ARQUIVO.get((emissor or "").lower(), _token(emissor or "")),
        _token(cliente or ""),
        _token(referencia or ""),
        _servico(orcamento or {}),
        ANEXO,
        f"R{max(0, int(revisao)):02d}",
    ]
    return "_".join(p for p in pedacos if p)


_RE_REVISAO = re.compile(r"_R\d{2,}$")


def com_revisao(nome: str, revisao: int) -> str:
    """O mesmo nome, na revisão pedida.

    Serve para o nome escrito à mão: reabrir a proposta sobe a revisão, e
    quem batizou o arquivo não quer perder o batismo para ganhar o `_R01`.
    """
    sufixo = f"R{max(0, int(revisao)):02d}"
    if _RE_REVISAO.search(nome):
        return _RE_REVISAO.sub(f"_{sufixo}", nome)
    return f"{nome}_{sufixo}" if nome else nome


_RE_PROIBIDO = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def limpar(nome: str) -> str:
    """Nome de arquivo escrito à mão, seguro para disco, R2 e download.

    Barra vira pasta no R2 e dois-pontos derruba o Windows; nada disso pode
    entrar num nome só porque alguém digitou.
    """
    return _RE_PROIBIDO.sub("", nome).strip(" .")


def nome_do_roll(emissor: str, versao: int = 0) -> str:
    """Como o roll se chama na versão `versao`, sem extensão.

        0 -> Roll_Flying
        1 -> Roll_Flying_Atl
        2 -> Roll_Flying_Atl_1
        3 -> Roll_Flying_Atl_2 ...

    "sempre salvamos como Roll_Flying -> Roll_Flying_Atl -> Roll_Flying_Atl_1
    e assim por diante". O `_Atl` da primeira atualização não leva número; a
    contagem começa na segunda.
    """
    base = f"Roll_{EMISSOR_NO_ARQUIVO.get((emissor or '').lower(), _token(emissor or ''))}"
    if versao <= 0:
        return base
    if versao == 1:
        return f"{base}_Atl"
    return f"{base}_Atl_{versao - 1}"
