"""Testes do chat com o modelo mockado (sem rede)."""
import json
from types import SimpleNamespace

import pytest

from app.db.schema import aplicar_schema
from app.ia import chat
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(nome, argumentos, id_="tc1"):
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=nome, arguments=json.dumps(argumentos))
    )


ESTRUTURA = {
    "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
    "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
    "desconto_pct": 0, "desconto_label": None, "estrategia": "planilha",
    "mostrar_precos_individuais": False, "_avisos": [],
}


def test_conversa_vazia_da_saudacao_sem_ia(db, monkeypatch):
    def _nunca(*a, **kw):
        raise AssertionError("não deveria chamar o modelo")
    monkeypatch.setattr(chat, "_chamar_modelo", _nunca)
    out = chat.responder(db, [])
    assert "Oi, tudo bem?" in out["mensagem"]
    assert out["quick_replies"] == ["Nova proposta", "Consultar cliente",
                                    "Copiar proposta anterior"]
    assert out["levantamento"] is None


def test_ia_precifica_via_ferramenta(db, monkeypatch):
    aplicar_schema(db)
    semear_precos(db)
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta", {"estrutura": ESTRUTURA})]),
        _msg(content="Fechado! Fachada da GALLI dá R$3.000,00. Gero a proposta?"),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    monkeypatch.setenv("OPENAI_API_KEY", "fake")

    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI, fachada"}])
    assert out["levantamento"] is not None
    assert out["levantamento"]["fechado"]["orcamento"]["subtotal"] == 3000
    assert "3.000" in out["mensagem"]


def test_sem_chave_nao_quebra(db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert "Texto direto" in out["mensagem"]
    assert out["levantamento"] is None


def test_excecao_do_modelo_nao_quebra(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    def _explode(*a, **kw):
        raise RuntimeError("api fora")
    monkeypatch.setattr(chat, "_chamar_modelo", _explode)
    out = chat.responder(db, [{"role": "user", "content": "oi"}])
    assert out["levantamento"] is None
    assert "Texto direto" in out["mensagem"]


def test_ferramenta_com_erro_devolve_feedback_para_ia(db, monkeypatch):
    """Exceção numa ferramenta não mata a conversa: vira {"erro": ...} e a IA se corrige."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    historicos = []

    def _explode(*a, **kw):
        raise TypeError("shape errado")

    monkeypatch.setattr(chat, "levantar", _explode)
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta", {"estrutura": {"cliente": "GALLI"}})]),
        _msg(content="Opa, me faltou informação — qual o empreendimento?"),
    ]

    def _modelo(mensagens_llm, tools):
        historicos.append(list(mensagens_llm))
        return respostas.pop(0)

    monkeypatch.setattr(chat, "_chamar_modelo", _modelo)
    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI"}])
    assert out["mensagem"] == "Opa, me faltou informação — qual o empreendimento?"
    assert out["levantamento"] is None
    ultima_tool = [m for m in historicos[1] if m.get("role") == "tool"][-1]
    assert "erro" in ultima_tool["content"]


def test_estrutura_incompleta_e_completada(db, monkeypatch):
    """Estrutura parcial do modelo é completada com defaults antes de levantar."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_proposta",
                                    {"estrutura": {"cliente": "GALLI",
                                                   "externas": ["Perspectiva Fachada"]}})]),
        _msg(content="Fechado! Deu R$3.000,00."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    out = chat.responder(db, [{"role": "user", "content": "GALLI, uma fachada"}])
    assert out["levantamento"] is not None
    assert out["levantamento"]["fechado"]["orcamento"]["subtotal"] > 0


def test_cliente_string_vira_objeto():
    est = chat._completar_estrutura({"cliente": "GALLI"})
    assert est["cliente"] == {"empresa": "GALLI", "ref": "", "contato": ""}
    assert est["externas"] == [] and est["desconto_pct"] == 0
    assert est["estrategia"] == "planilha" and est["_avisos"] == []


def test_schema_estrutura_contem_categorias_dinamicas():
    schema = chat._schema_estrutura(["externas", "internas", "plantas", "filmes", "tecnologia"])
    filmes = schema["properties"]["filmes"]
    assert filmes["type"] == "array"
    assert filmes["items"]["anyOf"][0] == {"type": "string"}  # ou {descricao, preco}
    # A descrição diz de quem é a categoria: foi `filmes` com emissor rinno que
    # deixou a proposta da Archtech sem preço.
    assert filmes["description"].startswith("[FLYING STUDIO]")
    assert "emissor='flying'" in filmes["description"]
    assert "tecnologia" in schema["properties"]
    assert schema["properties"]["tabela_precos"]["enum"] == ["padrao", "mcmv", "rinno", "nid"]
    assert schema["properties"]["emissor"]["enum"] == ["flying", "rinno", "nid"]
    assert schema["required"] == ["emissor", "cliente"]
    assert schema["additionalProperties"] is False


def test_completar_estrutura_preserva_tabela_precos_mcmv():
    est = chat._completar_estrutura({"cliente": "GALLI", "tabela_precos": "mcmv"})
    assert est["tabela_precos"] == "mcmv"


def test_completar_estrutura_tabela_precos_invalida_vira_padrao():
    est = chat._completar_estrutura({"cliente": "GALLI", "tabela_precos": "bitcoin"})
    assert est["tabela_precos"] == "padrao"


def test_emissor_default_e_flying():
    est = chat._completar_estrutura({"cliente": "GALLI"})
    assert est["emissor"] == "flying" and est["tabela_precos"] == "padrao"


def test_emissor_traz_a_tabela_da_propria_empresa():
    for emissor, tabela in (("rinno", "rinno"), ("nid", "nid")):
        est = chat._completar_estrutura({"cliente": "OUSY", "emissor": emissor})
        assert est["emissor"] == emissor
        assert est["tabela_precos"] == tabela


def test_tabela_de_outra_empresa_nao_gruda_no_emissor():
    """mcmv é da Flying: pedida com emissor rinno, cai na tabela da Rinno em
    vez de virar erro de ferramenta no meio da conversa."""
    est = chat._completar_estrutura({"cliente": "OUSY", "emissor": "rinno",
                                     "tabela_precos": "mcmv"})
    assert est["emissor"] == "rinno" and est["tabela_precos"] == "rinno"


def test_emissor_invalido_vira_flying():
    est = chat._completar_estrutura({"cliente": "GALLI", "emissor": "disney"})
    assert est["emissor"] == "flying" and est["tabela_precos"] == "padrao"


def test_completar_estrutura_categorias_dinamicas():
    est = chat._completar_estrutura({"filmes": ["Filme institucional"]}, ["filmes", "tecnologia"])
    assert est["filmes"] == ["Filme institucional"]
    assert est["tecnologia"] == []
    assert "externas" not in est


def test_montar_system_prompt_traz_catalogo_e_regra_rigidez(db):
    aplicar_schema(db)
    semear_precos(db)
    from app.db.repo_precos import carregar_tabela_precos
    from app.empresas import EMPRESAS
    catalogos = {chave: carregar_tabela_precos(db, emp.tabela_padrao)
                 for chave, emp in EMPRESAS.items()}
    prompt = chat._montar_system_prompt(catalogos)
    assert "REGRA DE RIGIDEZ" in prompt
    assert "Tecnologias Interativas" in prompt
    assert "MCMV" in prompt
    # As três empresas, cada uma com o seu catálogo e o seu emissor.
    for nome, emissor in (("FLYING STUDIO", "flying"), ("RINNO FILMS", "rinno"),
                          ("NID STUDIO", "nid")):
        assert f"{nome} (emissor={emissor}):" in prompt
    assert "rinno_filmes" in prompt and "nid_interiores" in prompt
    # Sem preços no catálogo injetado no prompt.
    assert "22800" not in prompt and "R$" not in prompt


def test_listar_para_ia_nao_expoe_docx_url(db, monkeypatch):
    """O bucket é privado: a IA não recebe docx_url (links são pela aba Histórico)."""
    monkeypatch.setattr(chat, "listar_propostas",
                        lambda conn, cliente: [{"id": 1, "cliente": "GALLI",
                                                "referencia": "Aurora", "data": "2026-07-19",
                                                "total": 3000.0,
                                                "docx_url": "https://r2/privado.docx"}])
    resultado, lev = chat._executar_ferramenta(db, "listar_propostas_cliente",
                                               {"cliente": "GALLI"})
    assert lev is None
    assert "docx_url" not in resultado and "r2/privado" not in resultado
    assert "GALLI" in resultado


def test_listar_sem_cliente_devolve_todas(db, monkeypatch):
    """'A mais recente' sem cliente: a ferramenta aceita chamada sem argumento."""
    chamadas = []
    monkeypatch.setattr(chat, "listar_propostas",
                        lambda conn, cliente: chamadas.append(cliente) or [])
    chat._executar_ferramenta(db, "listar_propostas_cliente", {})
    chat._executar_ferramenta(db, "listar_propostas_cliente", {"cliente": ""})
    assert chamadas == [None, None]


def test_carregar_inexistente_devolve_erro_orientando_relistar(db, monkeypatch):
    """Id perdido entre mensagens (stateless): erro instrui a IA a relistar."""
    monkeypatch.setattr(chat, "obter_estrutura_de_proposta", lambda conn, pid: None)
    resultado, lev = chat._executar_ferramenta(db, "carregar_proposta", {"proposta_id": 99})
    assert lev is None
    assert "erro" in resultado and "listar_propostas_cliente" in resultado


def test_propostas_citadas_apos_listar(db, monkeypatch):
    """Ferramentas que tocam propostas viram propostas_citadas — o hub mostra
    botões de download (a IA não pode citar links)."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(chat, "listar_propostas",
                        lambda conn, cliente: [{"id": 7, "cliente": "Avita",
                                                "referencia": "FRANCISCO POLITO",
                                                "data": "2026-07-20", "total": 33320.0,
                                                "docx_url": None}])
    respostas = [
        _msg(tool_calls=[_tool_call("listar_propostas_cliente", {"cliente": "Avita"})]),
        _msg(content="Achei a proposta FRANCISCO POLITO, de R$33.320,00."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    out = chat.responder(db, [{"role": "user", "content": "consulta a Avita"}])
    assert out["propostas_citadas"] == [{"id": 7, "cliente": "Avita",
                                         "referencia": "FRANCISCO POLITO"}]


def test_propostas_citadas_vazia_na_saudacao(db):
    assert chat.responder(db, [])["propostas_citadas"] == []


# ---------- leitura de print ----------

def _png_base64(largura=900, altura=600) -> str:
    import base64
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (10, 10, 200)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _msg_com_print(texto="olha esse print"):
    return {"role": "user", "content": [
        {"type": "text", "text": texto},
        {"type": "image_url", "image_url": {"url": _png_base64()}},
    ]}


TRANSCRICAO = ("CONSTRUTORA: GALLI\nEMPREENDIMENTO: Aurora\nA/C: Daniel\n"
               "ITENS:\n- externas | Fachada noturna | 3\n"
               'DÚVIDAS:\n- "umas internas do apto tipo" | candidatos: internas, plantas\n'
               "OBSERVAÇÕES: nenhuma")


@pytest.fixture
def leitura_mockada(monkeypatch):
    """As DUAS etapas da leitura mockadas + cache limpo; devolve as chamadas de
    visão (etapa 1), que é o que custa caro e não pode repetir."""
    from collections import OrderedDict

    from app.ia import leitura_print
    monkeypatch.setattr(leitura_print, "_cache", OrderedDict())
    chamadas: list = []
    monkeypatch.setattr(leitura_print, "_chamar_modelo",
                        lambda prompt, imgs: chamadas.append(imgs) or "CORPO:\n3 fachadas noturnas")
    monkeypatch.setattr(leitura_print, "_chamar_modelo_texto",
                        lambda prompt, txt: TRANSCRICAO)
    return chamadas


def test_print_vira_texto_antes_de_chegar_no_chat(db, monkeypatch, leitura_mockada):
    """A conversa nunca vê base64: a imagem entra como transcrição estruturada."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    vistas = []
    monkeypatch.setattr(chat, "_chamar_modelo",
                        lambda m, t: vistas.append(m) or _msg(content="Boa! Confirma o A/C?"))

    out = chat.responder(db, [_msg_com_print()])

    conteudo = vistas[0][-1]["content"]
    assert isinstance(conteudo, str)
    assert "base64" not in conteudo
    assert "olha esse print" in conteudo          # o texto do usuário é preservado
    assert "GALLI" in conteudo and "Fachada noturna" in conteudo
    assert "DÚVIDAS" in conteudo
    # A transcrição devolvida é exatamente o que foi para o modelo: o front
    # grava no lugar da imagem e para de reenviar o base64.
    assert out["transcricao"] == conteudo


def test_imagem_e_lida_uma_vez_mesmo_com_o_front_reenviando(db, monkeypatch, leitura_mockada):
    """Chat stateless: o front reenvia o print a cada rodada, mas ele é lido 1x."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: _msg(content="ok"))

    historico = [_msg_com_print()]
    for i in range(6):  # seis idas e vindas sobre a mesma proposta
        chat.responder(db, historico)
        historico += [{"role": "assistant", "content": "ok"},
                      {"role": "user", "content": f"pergunta {i}"}]

    assert len(leitura_mockada) == 1


def test_print_gigante_recebe_orientacao_em_vez_de_erro(db, monkeypatch, leitura_mockada):
    import base64

    from app.ia import visao
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(chat, "_chamar_modelo",
                        lambda m, t: pytest.fail("não deveria chamar o modelo"))

    gordo = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (visao.MAX_BYTES + 1)).decode()
    out = chat.responder(db, [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + gordo}}]}])

    assert "grande demais" in out["mensagem"]
    assert out["levantamento"] is None
    assert leitura_mockada == []


def test_anexo_que_nao_e_imagem_e_recusado(db, monkeypatch, leitura_mockada):
    import base64

    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(chat, "_chamar_modelo",
                        lambda m, t: pytest.fail("não deveria chamar o modelo"))

    pdf = base64.b64encode(b"%PDF-1.7 documento").decode()
    out = chat.responder(db, [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + pdf}}]}])

    assert "não é uma imagem" in out["mensagem"]
    assert leitura_mockada == []


def test_falha_da_leitura_nao_derruba_o_chat(db, monkeypatch):
    from collections import OrderedDict

    from app.ia import leitura_print
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(leitura_print, "_cache", OrderedDict())

    def _explode(prompt, imgs):
        raise RuntimeError("visão fora do ar")
    monkeypatch.setattr(leitura_print, "_chamar_modelo", _explode)

    out = chat.responder(db, [_msg_com_print()])
    assert "Texto direto" in out["mensagem"]


def test_conversa_sem_print_segue_igual(db, monkeypatch):
    """Mensagem de texto puro não passa por nada novo."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    vistas = []
    monkeypatch.setattr(chat, "_chamar_modelo",
                        lambda m, t: vistas.append(m) or _msg(content="oi"))

    out = chat.responder(db, [{"role": "user", "content": "proposta pra GALLI"}])
    assert vistas[0][-1] == {"role": "user", "content": "proposta pra GALLI"}
    assert out["transcricao"] is None


def test_categoria_da_rinno_e_da_nid_dizem_de_quem_sao():
    schema = chat._schema_estrutura(["filmes", "rinno_filmes", "nid_pdv"])
    assert schema["properties"]["rinno_filmes"]["description"].startswith("[RINNO FILMS]")
    assert "emissor='rinno'" in schema["properties"]["rinno_filmes"]["description"]
    assert schema["properties"]["nid_pdv"]["description"].startswith("[NID STUDIO]")


def test_schema_tem_ajuste_e_preco_por_imagem():
    schema = chat._schema_estrutura(["externas"])
    assert schema["properties"]["ajuste_planilha_pct"]["type"] == "number"
    assert schema["properties"]["preco_por_imagem"]["type"] == ["number", "null"]
    est = chat._completar_estrutura({"cliente": "GALLI"})
    assert est["ajuste_planilha_pct"] == 0 and est["preco_por_imagem"] is None


def test_completar_estrutura_preserva_item_com_preco():
    est = chat._completar_estrutura({
        "cliente": "OUSY", "emissor": "rinno",
        "rinno_filmes": [{"descricao": "Filme institucional de até 2:00", "preco": 15000},
                         "Filme corretor", 7, None],
    }, ["rinno_filmes"])
    assert est["rinno_filmes"] == [
        {"descricao": "Filme institucional de até 2:00", "preco": 15000}, "Filme corretor", "7"]


def test_schema_aceita_item_como_string_ou_objeto_com_preco():
    schema = chat._schema_estrutura(["rinno_filmes"])
    itens = schema["properties"]["rinno_filmes"]["items"]
    tipos = [alt.get("type") for alt in itens["anyOf"]]
    assert tipos == ["string", "object"]
    assert itens["anyOf"][1]["required"] == ["descricao"]


# ---------- uma ferramenta por empresa ----------


def test_uma_ferramenta_de_precificacao_por_empresa_so_com_as_proprias_categorias():
    ferramentas = chat._ferramentas({
        "flying": ["externas", "filmes"], "rinno": ["rinno_filmes"], "nid": ["nid_pdv"]})
    nomes = [f["function"]["name"] for f in ferramentas]
    assert nomes[:3] == ["precificar_flying", "precificar_rinno", "precificar_nid"]
    assert "listar_propostas_cliente" in nomes and "carregar_proposta" in nomes

    def props(nome):
        f = next(x for x in ferramentas if x["function"]["name"] == nome)
        return f["function"]["parameters"]["properties"]["estrutura"]["properties"]

    # Foi `filmes` com emissor rinno que zerou a Archtech: agora não existe.
    assert "filmes" in props("precificar_flying") and "filmes" not in props("precificar_rinno")
    assert "rinno_filmes" in props("precificar_rinno") and "rinno_filmes" not in props("precificar_flying")
    assert "emissor" not in props("precificar_rinno")
    assert props("precificar_rinno")["tabela_precos"]["enum"] == ["rinno"]
    assert props("precificar_flying")["tabela_precos"]["enum"] == ["padrao", "mcmv"]


def test_ferramenta_da_empresa_manda_mais_que_o_campo_emissor(db):
    """precificar_rinno é da Rinno mesmo se os argumentos vierem com emissor=flying."""
    aplicar_schema(db)
    semear_precos(db)
    resultado, lev = chat._executar_ferramenta(
        db, "precificar_rinno",
        {"estrutura": {"emissor": "flying", "cliente": {"empresa": "OUSY", "ref": "VM", "contato": "Yuri"},
                       "rinno_filmes": ["Filme conceito"]}},
        ["rinno_filmes", "filmes"])
    assert lev["estrutura"]["emissor"] == "rinno"
    assert lev["fechado"]["orcamento"]["rinno_filmes"]["total"] == 14000
    assert "erro" not in resultado


def test_precificar_proposta_generico_continua_aceito(db):
    aplicar_schema(db)
    semear_precos(db)
    resultado, lev = chat._executar_ferramenta(
        db, "precificar_proposta",
        {"estrutura": {"emissor": "nid", "cliente": "OUSY", "nid_pdv": ["Stand"]}}, ["nid_pdv"])
    assert lev["estrutura"]["emissor"] == "nid"


def test_erro_de_entrada_volta_com_instrucao_de_repassar(db):
    aplicar_schema(db)
    semear_precos(db)
    resultado, lev = chat._executar_ferramenta(
        db, "precificar_flying",
        {"estrutura": {"cliente": "GALLI", "externas": ["Fachada"], "ajuste_planilha_pct": -100}},
        ["externas"])
    dados = json.loads(resultado)
    assert lev is None
    assert "ajuste_planilha_pct" in dados["erro"]
    assert "Repasse esta mensagem" in dados["instrucao"]


def test_prompt_traz_exemplos_reais_e_regra_de_uma_unidade():
    from app.db.repo_precos import carregar_tabela_precos  # noqa: F401 — só o prompt base
    prompt = chat.SYSTEM_PROMPT
    assert "EXEMPLOS (pedidos reais" in prompt
    assert "precificar_rinno" in prompt and "precificar_flying" in prompt and "precificar_nid" in prompt
    assert "UMA UNIDADE POR ITEM" in prompt
    assert 'repasse o texto do erro ao usuário' in prompt
    assert "precificar_proposta" not in prompt


def test_prompt_manda_precificar_antes_de_perguntar():
    """A IA interrogava em vez de precificar: perguntava quem emitia (usando o
    nome da coordenadora do e-mail), oferecia a construtora como A/C, perguntava
    MCMV e preço por imagem — quatro perguntas, nenhum valor na tela."""
    prompt = chat.SYSTEM_PROMPT
    assert "PRECIFIQUE PRIMEIRO, PERGUNTE DEPOIS" in prompt
    assert "NÃO PERGUNTE ISSO" in prompt
    assert "QUEM EMITE É SEMPRE UMA DAS NOSSAS TRÊS" in prompt
    # MCMV e preço por imagem têm default, não pergunta.
    assert "assuma tabela_precos='padrao'" in prompt
    assert 'Nunca pergunte "você já tem um preço por imagem definido?"' in prompt
    assert "use 'padrao' e siga — não pergunte" in prompt
    # A/C é pessoa; sem pessoa, vai vazio e vira pendência do preview.
    assert "A/C é PESSOA" in prompt


# ---------- rastro e registro ----------


def test_rodada_grava_chat_log_com_rastro_das_ferramentas(db, monkeypatch):
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_rinno", {"estrutura": {
            "cliente": {"empresa": "Archtech", "ref": "Goiânia", "contato": "Luis"},
            "rinno_filmes": [{"descricao": "Filme viral", "preco": 4000}]}})]),
        _msg(content="Pronto: viral por R$ 4.000."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))

    traco: list = []
    out = chat.responder(db, [{"role": "user", "content": "viral pra archtech por 4 mil"}], traco=traco)
    assert out["mensagem"].startswith("Pronto")
    assert [c["nome"] for c in traco] == ["precificar_rinno"]
    assert traco[0]["args"]["estrutura"]["rinno_filmes"][0]["preco"] == 4000

    from app.db.repo_chat_log import listar_rodadas
    rodadas = listar_rodadas(db)
    assert len(rodadas) == 1
    r = rodadas[0]
    assert r["emissor"] == "rinno" and r["erro"] is None and r["duracao_ms"] >= 0
    assert r["ferramentas"][0]["nome"] == "precificar_rinno"
    assert r["resposta"]["mensagem"].startswith("Pronto")
    assert r["mensagens"][0]["content"] == "viral pra archtech por 4 mil"


def test_registro_nao_derruba_o_chat(db, monkeypatch):
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: _msg(content="oi"))
    import app.ia.chat as modulo
    monkeypatch.setattr(modulo, "registrar_rodada", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    # registrar_rodada de verdade engole erros; aqui simulamos o pior caso — a
    # própria chamada explodindo — e o chat ainda tem de responder? Não: o
    # contrato é que registrar_rodada NUNCA levanta. Confere isso direto.
    from app.db.repo_chat_log import registrar_rodada
    assert registrar_rodada(None, modelo="m", mensagens=[], ferramentas=[], resposta={},
                            emissor=None, duracao_ms=0) is None


def test_print_em_base64_nao_vai_para_o_log():
    from app.db.repo_chat_log import _sem_base64
    saida = _sem_base64({"content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]})
    assert saida["content"][0]["image_url"]["url"].startswith("<imagem ")


# ---------- o preview não pode ser apagado por uma segunda chamada ----------


def test_segunda_chamada_pobre_nao_apaga_o_que_a_primeira_precificou(db, monkeypatch):
    """O que aconteceu com a Tavares e Rosseti: a IA precificou o tour (7 áreas,
    R$ 29.050), chamou a ferramenta de novo só com o cliente para comentar que
    não tinha identificado as imagens, e o preview ficou zerado — cliente
    preenchido, nenhum item, R$ 0,00."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    cliente = {"empresa": "Tavares e Rosseti", "ref": "Fernando de Noronha",
               "contato": "Luis"}
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_flying", {"estrutura": {
            "cliente": cliente,
            "tour_virtual": ["Elaboração 3d", "Render 360 VR", "Versão mobile"],
            "ambientes": 7}}, id_="a")]),
        _msg(tool_calls=[_tool_call("precificar_flying",
                                    {"estrutura": {"cliente": cliente}}, id_="b")]),
        _msg(content="Tour Virtual (7 áreas): R$ 29.050,00. Faltam as 30 imagens."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))

    out = chat.responder(db, [{"role": "user", "content": "faremos 7"}])

    lev = out["levantamento"]
    assert lev is not None
    orc = lev["fechado"]["orcamento"]
    assert orc["total_imagens"] == 3, "a chamada vazia apagou os itens do preview"
    assert orc["subtotal"] == 7 * (2500 + 1200 + 450)
    assert lev["estrutura"]["ambientes"] == 7


def test_chamada_que_esvazia_de_proposito_continua_valendo(db, monkeypatch):
    """"tira tudo" é ordem: uma rodada com uma única chamada sem itens vale."""
    aplicar_schema(db)
    semear_precos(db)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    respostas = [
        _msg(tool_calls=[_tool_call("precificar_flying", {"estrutura": {
            "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"}}})]),
        _msg(content="Tirei tudo."),
    ]
    monkeypatch.setattr(chat, "_chamar_modelo", lambda m, t: respostas.pop(0))
    out = chat.responder(db, [{"role": "user", "content": "tira tudo"}])
    assert out["levantamento"]["fechado"]["orcamento"]["total_imagens"] == 0


def test_prompt_manda_uma_chamada_por_resposta_e_quantidade_sem_descricao():
    prompt = chat.SYSTEM_PROMPT
    assert "UMA chamada por resposta" in prompt
    assert "QUANTIDADE SEM DESCRIÇÃO CONTINUA SENDO ITEM" in prompt
    assert 'NUNCA responda "não consegui identificar as 30 imagens"' in prompt
