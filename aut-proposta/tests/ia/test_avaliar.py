"""O avaliador dos casos-ouro: confere chamadas sem precisar da IA."""
import json

from scripts.avaliar_chat import (CASOS_DIR, _linhas_de_itens, carregar_casos,
                                  ultima_precificacao, verificar, verificar_leitura)

CHAVES_ESPERADO = {"ferramenta", "cliente", "categorias", "sem_categorias", "preco_por_imagem",
                   "ajuste_planilha_pct", "desconto_pct", "quantidade_total", "quantidade_minima",
                   "nao_perguntar", "perguntar", "descricao_contem", "total_fechado"}
# Caso de leitura de print (tem `literal`): mede a etapa 2, não a conversa.
CHAVES_LEITURA = {"itens_total", "itens_minimo", "contem", "ac", "ac_nao", "construtora",
                  "construtora_nao", "empreendimento", "empreendimento_nao", "por_categoria"}

BLOCO = """CONSTRUTORA: SAE Engenharia e Marcante
EMPREENDIMENTO: SAE | GUANÁS
A/C: Thais Bastos
ITENS:
- externas | Fachada frente + lateral direita dia | 1
- plantas | Implantação 2º ao 13º Pavimento Tipo | 1
- internas | Coworking | 1
DÚVIDAS:
- nenhuma
OBSERVAÇÕES: nenhuma"""


def test_todos_os_casos_sao_bem_formados():
    casos = carregar_casos()
    assert len(casos) >= 8
    for nome, caso in casos.items():
        assert caso["origem"], nome
        if caso.get("literal"):
            assert set(caso["esperado"]) <= CHAVES_LEITURA, (nome, set(caso["esperado"]))
            continue
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


# ---------- leitura de print (etapa 2) ----------


def test_conta_so_as_linhas_de_itens_do_bloco():
    assert _linhas_de_itens(BLOCO) == [
        "externas | Fachada frente + lateral direita dia | 1",
        "plantas | Implantação 2º ao 13º Pavimento Tipo | 1",
        "internas | Coworking | 1",
    ]
    # "nenhum item claro" não conta como item.
    assert _linhas_de_itens("ITENS:\n- nenhum item claro\nDÚVIDAS:\n- nenhuma") == []


def test_leitura_reprova_quando_a_lista_encolhe():
    """O erro real: 39 itens no e-mail, 11 no preview."""
    falhas = verificar_leitura({"itens_total": 39}, BLOCO)
    assert falhas and "esperava 39, veio 3" in falhas[0]
    assert verificar_leitura({"itens_total": 3, "itens_minimo": 3}, BLOCO) == []


def test_leitura_reprova_ac_que_e_gente_nossa():
    nosso = BLOCO.replace("A/C: Thais Bastos", "A/C: Max Barbosa")
    falhas = verificar_leitura({"ac": "thais", "ac_nao": "max|lucas"}, nosso)
    assert len(falhas) == 2                      # não é a Thais, e é o Max
    assert any("é gente nossa" in f for f in falhas)
    assert verificar_leitura({"ac": "thais", "ac_nao": "max|lucas"}, BLOCO) == []


def test_leitura_cobra_faixa_de_andar_como_esta_no_print():
    encolhido = BLOCO.replace("2º ao 13º", "2º ao 3º")
    assert verificar_leitura({"contem": ["2º ao 13º|2o ao 13o"]}, encolhido)
    assert verificar_leitura({"contem": ["2º ao 13º|2o ao 13o"]}, BLOCO) == []


def test_leitura_confere_quantidade_por_categoria():
    assert verificar_leitura({"por_categoria": {"externas": 1, "internas": 1}}, BLOCO) == []
    falhas = verificar_leitura({"por_categoria": {"internas": 12}}, BLOCO)
    assert falhas and "esperava 12 itens, veio 1" in falhas[0]


def test_avaliador_cobra_a_pergunta_que_muda_o_preco():
    """Tour virtual é por ambiente: não perguntar quantas áreas é reprovação."""
    esperado = {"perguntar": ["quantas areas|quantos ambientes"]}
    calado = verificar(esperado, "precificar_flying",
                       {"cliente": {"empresa": "Maskin"}, "tour_virtual": ["Render 360"]},
                       ["Pronto, o tour ficou R$ 4.150."])
    assert calado and "NÃO perguntou" in calado[0]

    perguntou = verificar(esperado, "precificar_flying",
                          {"cliente": {"empresa": "Maskin"}, "tour_virtual": ["Render 360"]},
                          ["Quantas áreas de lazer o empreendimento tem?"])
    assert perguntou == []
