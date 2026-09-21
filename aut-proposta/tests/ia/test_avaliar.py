"""O avaliador dos casos-ouro: confere chamadas sem precisar da IA."""
import json

from scripts.avaliar_chat import CASOS_DIR, carregar_casos, ultima_precificacao, verificar

CHAVES_ESPERADO = {"ferramenta", "cliente", "categorias", "sem_categorias", "preco_por_imagem",
                   "ajuste_planilha_pct", "desconto_pct", "quantidade_total", "quantidade_minima",
                   "nao_perguntar", "descricao_contem"}


def test_todos_os_casos_sao_bem_formados():
    casos = carregar_casos()
    assert len(casos) >= 8
    for nome, caso in casos.items():
        assert caso["origem"], nome
        assert caso["turnos"] and all(isinstance(t, str) for t in caso["turnos"]), nome
        assert set(caso["esperado"]) <= CHAVES_ESPERADO, (nome, set(caso["esperado"]) - CHAVES_ESPERADO)
        assert caso["esperado"]["ferramenta"].startswith("precificar_"), nome


def test_caso_archtech_aprova_a_chamada_certa_e_reprova_a_errada():
    caso = json.loads((CASOS_DIR / "archtech_viral_4k.json").read_text(encoding="utf-8"))
    certa = {"cliente": {"empresa": "Archtech", "ref": "GOIANIA", "contato": "Luis"},
             "rinno_filmes": [{"descricao": "Filme viral de até 1:00 em 4K", "preco": 4000}]}
    assert verificar(caso["esperado"], "precificar_rinno", certa, ["Pronto!"]) == []

    # O erro real: ferramenta certa, categoria da Flying e sem o preço dito.
    errada = {"cliente": {"empresa": "Archtech", "ref": "GOIANIA", "contato": "Luis"},
              "filmes": ["Filme viral"]}
    falhas = verificar(caso["esperado"], "precificar_rinno", errada, [])
    assert any("rinno_filmes" in f for f in falhas)
    assert any("filmes não deveria" in f for f in falhas)


def test_pergunta_proibida_reprova():
    caso = json.loads((CASOS_DIR / "archtech_institucional.json").read_text(encoding="utf-8"))
    estrutura = {"cliente": {"empresa": "Archtech", "ref": "Consolação", "contato": "Francisco"},
                 "rinno_filmes": ["Filme institucional"]}
    assert verificar(caso["esperado"], "precificar_rinno", estrutura, ["Feito."]) == []
    falhas = verificar(caso["esperado"], "precificar_rinno", estrutura,
                       ["Quantas unidades do filme institucional?"])
    assert falhas == ["a IA perguntou 'quantas unidades', e não devia"]


def test_sem_chamada_e_falha_com_a_resposta_da_ia():
    caso = json.loads((CASOS_DIR / "ousy_rinno_tres_filmes.json").read_text(encoding="utf-8"))
    falhas = verificar(caso["esperado"], None, None, ["Qual o valor de cada filme?"])
    assert falhas and "nenhuma chamada" in falhas[0] and "Qual o valor" in falhas[0]


def test_ultima_precificacao_do_traco():
    traco = [{"nome": "listar_propostas_cliente", "args": {}, "resultado": "[]"},
             {"nome": "precificar_flying", "args": {"estrutura": {"cliente": "A"}}, "resultado": "{}"},
             {"nome": "precificar_rinno", "args": {"estrutura": {"cliente": "B"}}, "resultado": "{}"}]
    assert ultima_precificacao(traco) == ("precificar_rinno", {"cliente": "B"})
    assert ultima_precificacao([]) == (None, None)
