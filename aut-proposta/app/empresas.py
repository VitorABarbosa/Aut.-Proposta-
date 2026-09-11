"""As três empresas do grupo que emitem proposta: Flying, Rinno e NID.

O `emissor` decide três coisas, e só elas: quais tabelas de preço valem, qual
timbrado abre o .docx e qual gerador escreve o corpo. Todo o resto —
orçamento, desconto, histórico do cliente, persistência — é comum às três.

Cuidado com o nome: `emissor` é qual das NOSSAS empresas assina a proposta;
`cliente.empresa` continua sendo a construtora/incorporadora que recebe.

As categorias de preço de Rinno e NID são prefixadas (`rinno_*`, `nid_*`)
porque o chat monta um catálogo único com as três empresas — sem prefixo,
`filmes` da Flying e `filmes` da Rinno colidiriam no schema da ferramenta.
As categorias da Flying ficam sem prefixo: são as que já existem no banco e
nas propostas gravadas.
"""
from __future__ import annotations

from dataclasses import dataclass

EMISSOR_PADRAO = "flying"


@dataclass(frozen=True)
class Margens:
    """Margens do corpo em cm. O timbrado traz as suas, pensadas para a arte
    (a da NID tem margem esquerda zero porque a faixa do cabeçalho sangra a
    página inteira); estas são as do TEXTO."""

    esquerda: float
    direita: float
    topo: float
    base: float


@dataclass(frozen=True)
class Empresa:
    chave: str
    nome: str
    titulo_proposta: str
    tabelas: tuple[str, ...]  # tabelas de preço válidas; a 1ª é o default
    timbrado: str
    margens: Margens

    @property
    def tabela_padrao(self) -> str:
        return self.tabelas[0]


EMPRESAS: dict[str, Empresa] = {
    "flying": Empresa(
        chave="flying",
        nome="FLYING STUDIO",
        titulo_proposta="PROPOSTA DE IMAGENS, FILMES E TECNOLOGIAS 3D",
        tabelas=("padrao", "mcmv"),
        timbrado="TIMBRADO_FLYINGSTUDIO.docx",
        margens=Margens(esquerda=3.0, direita=3.0, topo=2.5, base=1.5),
    ),
    "rinno": Empresa(
        chave="rinno",
        nome="RINNO FILMS",
        titulo_proposta="PROPOSTA DE FILMES E TECNOLOGIAS 3D",
        tabelas=("rinno",),
        timbrado="TIMBRADO_RINNO.docx",
        margens=Margens(esquerda=2.3, direita=2.3, topo=2.9, base=4.0),
    ),
    "nid": Empresa(
        chave="nid",
        nome="NID STUDIO",
        titulo_proposta="NID STUDIO – SEU NINHO CRIATIVO",
        tabelas=("nid",),
        timbrado="TIMBRADO_NID.docx",
        margens=Margens(esquerda=3.0, direita=3.0, topo=2.5, base=2.5),
    ),
}

EMISSORES = tuple(EMPRESAS)


def empresa(emissor: str | None) -> Empresa:
    """Empresa emissora. `None`/vazio cai na Flying — propostas gravadas antes
    do multi-empresa não têm o campo."""
    chave = (emissor or EMISSOR_PADRAO).strip().lower()
    if chave not in EMPRESAS:
        raise ValueError(f"emissor inválido: {emissor!r} (válidos: {EMISSORES})")
    return EMPRESAS[chave]


def resolver_tabela(emissor: str | None, tabela_precos: str | None) -> str:
    """Tabela de preços a usar, validada contra o emissor.

    Sem tabela pedida, devolve a padrão da empresa. Tabela que não é daquela
    empresa é erro de entrada, não silêncio: pedir 'mcmv' para a Rinno é o
    tipo de engano que sairia como proposta errada no cliente.
    """
    emp = empresa(emissor)
    if not tabela_precos:
        return emp.tabela_padrao
    if tabela_precos not in emp.tabelas:
        raise ValueError(
            f"tabela_precos {tabela_precos!r} não é da {emp.nome} "
            f"(válidas: {emp.tabelas})"
        )
    return tabela_precos


def emissor_da_tabela(tabela_precos: str) -> str:
    """Emissor dono da tabela. Usado para migrar proposta antiga, que tem
    tabela gravada mas não tem emissor."""
    for emp in EMPRESAS.values():
        if tabela_precos in emp.tabelas:
            return emp.chave
    return EMISSOR_PADRAO
