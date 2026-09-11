from pathlib import Path

import pytest

from app.db.repo_propostas import salvar_proposta, upsert_cliente
from app.db.schema import aplicar_schema
from app.servicos import proposta as svc
from scripts.seed_precos import semear_precos

pytestmark = pytest.mark.db


def _estrutura(estrategia="planilha", empresa="GALLI", desconto=0.0):
    return {
        "cliente": {"empresa": empresa, "ref": "Residencial Aurora", "contato": "Daniel"},
        "externas": ["Fachada vista da calçada"],
        "internas": ["Academia"],
        "plantas": ["Apartamento Tipo"],
        "desconto_pct": desconto,
        "desconto_label": "parceria" if desconto else None,
        "estrategia": estrategia,
        "mostrar_precos_individuais": False,
        "_avisos": [],
    }


def _prep(db):
    aplicar_schema(db)
    semear_precos(db)


def test_parse_texto_passa_categorias_do_catalogo_ao_parser(db, monkeypatch):
    _prep(db)
    recebido = {}

    def _parse_fake(texto, categorias=None):
        recebido["texto"] = texto
        recebido["categorias"] = categorias
        return {"cliente": {"empresa": "GALLI"}}

    monkeypatch.setattr("app.ia.parser.parse", _parse_fake)
    out = svc.parse_texto(db, "Cliente: GALLI\nFilmes: Filme institucional")
    assert out["cliente"]["empresa"] == "GALLI"
    assert "filmes" in recebido["categorias"]
    assert "tecnologia" in recebido["categorias"]


def test_levantar_planilha_precos_do_banco(db):
    _prep(db)
    out = svc.levantar(db, _estrutura())
    orc = out["fechado"]["orcamento"]
    assert out["estrategia_usada"] == "planilha"
    assert orc["externas"]["itens"][0]["preco"] == 3000  # fachada, preço do NEON
    assert orc["total_imagens"] == 3
    assert out["tabela_precos"] == "padrao"


def test_levantar_devolve_tabela_precos_padrao_por_default(db):
    _prep(db)
    out = svc.levantar(db, _estrutura())
    assert out["tabela_precos"] == "padrao"


def test_levantar_mcmv_precifica_interna_1500(db):
    _prep(db)
    est = _estrutura()
    est["tabela_precos"] = "mcmv"
    est["externas"] = []
    est["internas"] = ["Academia"]
    est["plantas"] = []
    out = svc.levantar(db, est)
    assert out["tabela_precos"] == "mcmv"
    assert out["fechado"]["orcamento"]["internas"]["itens"][0]["preco"] == 1500


def test_levantar_tabela_precos_invalida_levanta_erro(db):
    _prep(db)
    est = _estrutura()
    est["tabela_precos"] = "inexistente"
    with pytest.raises(ValueError):
        svc.levantar(db, est)


def test_levantar_com_desconto(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(desconto=10.0))
    fin = out["fechado"]["financeiro"]
    assert fin["desconto_pct"] == 10.0
    assert fin["total"] == pytest.approx(fin["subtotal"] * 0.9)
    assert fin["rotulo"] == "parceria"


def test_levantar_auto_usa_historico_quando_cliente_existe(db):
    _prep(db)
    cid = upsert_cliente(db, "BRNPAR")
    salvar_proposta(db, cid, {
        "orcamento": {
            "estrategia": "planilha", "subtotal": 1800, "total_imagens": 1,
            "externas": {"nome": "externas", "qtd": 0, "total": 0, "itens": []},
            "internas": {"nome": "internas", "qtd": 1, "total": 1800,
                         "itens": [{"descricao": "Perspectiva Academia", "preco": 1800,
                                    "fonte": "manual"}]},
            "plantas": {"nome": "plantas", "qtd": 0, "total": 0, "itens": []},
        },
        "financeiro": {"subtotal": 1800, "desconto_pct": 0.0, "desconto_valor": 0.0,
                       "total": 1800.0, "rotulo": ""},
    })
    est = _estrutura(estrategia="auto", empresa="BRNPAR")
    est["externas"] = []
    est["plantas"] = []
    est["internas"] = ["Perspectiva Academia"]
    out = svc.levantar(db, est)
    assert out["estrategia_usada"].startswith("historico")
    assert out["fechado"]["orcamento"]["internas"]["itens"][0]["preco"] == 1800


def test_levantar_auto_sem_historico_cai_na_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="auto", empresa="CLIENTE NOVO"))
    assert out["estrategia_usada"] == "planilha"


def test_levantar_historico_sem_cliente_avisa_e_usa_planilha(db):
    _prep(db)
    out = svc.levantar(db, _estrutura(estrategia="historico", empresa="SEM HISTORICO"))
    assert out["estrategia_usada"] == "planilha"
    assert any("histórico" in a.lower() for a in out["avisos"])


def test_gerar_salva_docx_e_proposta(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)  # sem R2
    out = svc.gerar(db, _estrutura(desconto=10.0), tmp_path)

    assert out["proposta_id"] >= 1
    docx = Path(out["docx_path"])
    assert docx.exists() and docx.name == f"proposta_{out['proposta_id']}.docx"
    assert out["docx_url"] is None

    with db.cursor() as cur:
        cur.execute("SELECT subtotal, docx_url FROM propostas WHERE id = %s",
                    (out["proposta_id"],))
        subtotal, docx_url = cur.fetchone()
    assert subtotal == out["fechado"]["orcamento"]["subtotal"]
    assert docx_url is None


def test_gerar_com_r2_grava_url(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: f"https://r2.exemplo/{chave}")
    out = svc.gerar(db, _estrutura(), tmp_path)
    assert out["docx_url"] == f"https://r2.exemplo/{out['chave_r2']}"
    with db.cursor() as cur:
        cur.execute("SELECT docx_url FROM propostas WHERE id = %s", (out["proposta_id"],))
        assert cur.fetchone()[0] == out["docx_url"]


def test_gerar_persiste_apos_fechar_conexao(db, tmp_path, monkeypatch):
    """Regressão: os SELECTs de levantar abrem transação implícita e os
    conn.transaction() dos repos viram SAVEPOINTs — sem commit final, o
    close() da conexão descartava a proposta (visto na verificação real)."""
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    out = svc.gerar(db, _estrutura(), tmp_path)

    # Verifica numa SEGUNDA conexão: só enxerga o que foi de fato commitado.
    from tests.conftest import DSN_TESTE
    from app.db.conexao import get_conn

    outra = get_conn(DSN_TESTE)
    try:
        with outra.cursor() as cur:
            cur.execute("SELECT count(*) FROM propostas WHERE id = %s", (out["proposta_id"],))
            assert cur.fetchone()[0] == 1
    finally:
        outra.close()


def test_gerar_usa_chave_organizada_por_cliente_projeto(db, tmp_path, monkeypatch):
    _prep(db)
    chaves = []
    monkeypatch.setattr(svc, "enviar_docx",
                        lambda caminho, chave: (chaves.append(chave),
                                                f"https://r2/{chave}")[1])
    out = svc.gerar(db, _estrutura(), tmp_path)
    # O emissor abre o caminho: o mesmo cliente/projeto pode ter proposta das
    # três empresas, e no R2 elas não se misturam.
    esperado = f"Propostas/flying/galli/residencial-aurora/proposta_{out['proposta_id']}.docx"
    assert chaves == [esperado]
    assert out["chave_r2"] == esperado


def test_categoria_fora_da_tabela_gera_aviso(db):
    """Item de categoria inexistente na tabela escolhida (ex.: tecnologia no
    mcmv) não pode sumir em silêncio — vira aviso."""
    _prep(db)
    est = _estrutura()
    est["tabela_precos"] = "mcmv"
    est["tecnologia"] = ["Aplicativo touch para o stand"]
    out = svc.levantar(db, est)
    assert any("tecnologia" in a and "mcmv" in a for a in out["avisos"])
    assert any("1 item(ns) não precificado" in a for a in out["avisos"])


# ---------- multi-empresa ----------


def _estrutura_rinno():
    return {
        "cliente": {"empresa": "OUSY", "ref": "Vila Mariana", "contato": "Yuri"},
        "emissor": "rinno",
        "rinno_filmes": ["Filme conceito", "Filme corretor"],
        "rinno_takes": ["Take IA da piscina"],
        "desconto_pct": 0.0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }


def test_levantar_da_rinno_usa_a_tabela_da_rinno(db):
    _prep(db)
    out = svc.levantar(db, _estrutura_rinno())

    assert out["emissor"] == "rinno" and out["tabela_precos"] == "rinno"
    orc = out["fechado"]["orcamento"]
    assert orc["rinno_filmes"]["total"] == 24000   # conceito 14000 + produto 10000
    assert orc["rinno_takes"]["total"] == 650
    assert out["fechado"]["financeiro"]["total"] == 24650.0


def test_item_de_servico_sai_com_o_nome_do_catalogo(db):
    """Imagem preserva a cena escrita pelo usuário; serviço sai com o nome
    comercial — 'Filme corretor' vira 'Filme Corretor / Produto de até 1:30'."""
    _prep(db)
    out = svc.levantar(db, _estrutura_rinno())
    descricoes = [i["descricao"] for i in out["fechado"]["orcamento"]["rinno_filmes"]["itens"]]
    assert descricoes == ["Filme Conceito de até 2:30 (Dois Minutos e Meio)",
                          "Filme Corretor / Produto de até 1:30 (Um Minuto e Meio)"]

    lev_flying = svc.levantar(db, _estrutura())
    externas = lev_flying["fechado"]["orcamento"]["externas"]["itens"]
    assert externas[0]["descricao"] == "Perspectiva Fachada vista da calçada"


def test_emissor_fica_gravado_e_volta_na_listagem_e_na_copia(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    out = svc.gerar(db, _estrutura_rinno(), tmp_path)

    from app.db.repo_propostas import listar_propostas, obter_estrutura_de_proposta
    assert out["emissor"] == "rinno"
    assert listar_propostas(db)[0]["emissor"] == "rinno"
    copia = obter_estrutura_de_proposta(db, out["proposta_id"])
    assert copia["emissor"] == "rinno" and copia["tabela_precos"] == "rinno"


def test_proposta_sem_emissor_continua_sendo_flying(db, tmp_path, monkeypatch):
    """Estrutura antiga (sem o campo) não pode quebrar nem trocar de empresa."""
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    out = svc.gerar(db, _estrutura(), tmp_path)
    assert out["emissor"] == "flying"
    from app.db.repo_propostas import listar_propostas
    assert listar_propostas(db)[0]["emissor"] == "flying"


def test_tabela_de_outra_empresa_no_levantamento_e_erro(db):
    _prep(db)
    est = _estrutura_rinno() | {"tabela_precos": "mcmv"}
    with pytest.raises(ValueError, match="não é da RINNO FILMS"):
        svc.levantar(db, est)


def test_gerar_da_nid_escreve_o_docx_da_nid(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    est = {
        "cliente": {"empresa": "OUSY", "ref": "Vila Mariana", "contato": "Yuri"},
        "emissor": "nid",
        "nid_fachada": ["Design de fachada"],
        "nid_pdv": ["Stand de vendas"],
        "desconto_pct": 0.0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    out = svc.gerar(db, est, tmp_path)

    assert out["fechado"]["financeiro"]["total"] == 47000.0  # 22000 + 25000
    assert out["chave_r2"].startswith("Propostas/nid/ousy/vila-mariana/")

    from docx import Document
    texto = "\n".join(p.text for p in Document(out["docx_path"]).paragraphs)
    assert texto.startswith("NID STUDIO – SEU NINHO CRIATIVO")
    assert "Lâmina 07: Planta de Construir e Demolir" in texto


# ---------- o caso da Archtech: categoria da Flying com emissor rinno ----------


def test_filme_em_categoria_da_flying_com_emissor_rinno_e_precificado(db):
    """Foi o teste real que falhou: a IA mandou `filmes` (Flying) com emissor
    rinno e a proposta saiu sem preço, com aviso de categoria inexistente."""
    _prep(db)
    est = {
        "cliente": {"empresa": "Archtech", "ref": "Consolação", "contato": "Francisco"},
        "emissor": "rinno",
        "filmes": ["Filme institucional"],
        "desconto_pct": 0.0, "desconto_label": None, "estrategia": "planilha",
        "mostrar_precos_individuais": False, "_avisos": [],
    }
    out = svc.levantar(db, est)

    assert out["fechado"]["orcamento"]["rinno_filmes"]["total"] == 18000
    assert out["fechado"]["financeiro"]["total"] == 18000.0
    assert not any("não existe" in a for a in out["avisos"])
    # E a estrutura devolvida já está no namespace certo, para o preview.
    assert out["estrutura"]["rinno_filmes"] == ["Filme institucional"]
    assert "filmes" not in out["estrutura"]


def test_remap_nunca_cruza_de_uma_empresa_para_outra(db):
    """`rinno_filmes` com emissor flying não vira `filmes`: são produtos
    diferentes. Fica o aviso, como antes."""
    _prep(db)
    est = _estrutura() | {"rinno_filmes": ["Filme conceito"]}
    out = svc.levantar(db, est)
    assert any("rinno_filmes" in a and "não existe" in a for a in out["avisos"])


def test_no_namespace_do_emissor_junta_com_o_que_ja_existia():
    est = {"filmes": ["a"], "rinno_filmes": ["b"], "_avisos": [], "cliente": {}}
    out = svc.no_namespace_do_emissor(est, "rinno", ["rinno_filmes", "rinno_takes"])
    assert out["rinno_filmes"] == ["b", "a"] and "filmes" not in out


# ---------- ajuste sobre a planilha e preço fixo por imagem ----------


def test_planilha_mais_dez_por_cento_entra_no_preco_de_cada_item(db):
    """Cliente novo: planilha + 10%. Fachada 3000 -> 3300, academia 1750 -> 1925,
    planta tipo 1200 -> 1320. Sem linha de desconto: o cliente vê só os preços."""
    _prep(db)
    out = svc.levantar(db, _estrutura() | {"ajuste_planilha_pct": 10})
    orc = out["fechado"]["orcamento"]
    assert orc["externas"]["itens"][0]["preco"] == 3300
    assert orc["internas"]["itens"][0]["preco"] == 1925
    assert orc["plantas"]["itens"][0]["preco"] == 1320
    assert orc["externas"]["itens"][0]["fonte"] == "planilha+10%:fachada"
    assert out["fechado"]["financeiro"]["desconto_pct"] == 0
    assert out["fechado"]["financeiro"]["total"] == 6545.0


def test_planilha_menos_cinco_por_cento(db):
    _prep(db)
    out = svc.levantar(db, _estrutura() | {"ajuste_planilha_pct": -5})
    assert out["fechado"]["orcamento"]["externas"]["itens"][0]["preco"] == 2850


def test_preco_fixo_por_imagem_vale_para_toda_imagem_e_nada_mais(db):
    """UNICOS/João Casseb: 12 imagens diferentes a 2.400 cada. Fachada,
    academia e planta saem por 2.400; o app touch continua na tabela."""
    _prep(db)
    est = _estrutura() | {"preco_por_imagem": 2400, "tecnologia": ["App touch para o stand"]}
    out = svc.levantar(db, est)
    orc = out["fechado"]["orcamento"]
    for cat in ("externas", "internas", "plantas"):
        assert orc[cat]["itens"][0]["preco"] == 2400
        assert orc[cat]["itens"][0]["fonte"] == "fixo_por_imagem"
    assert orc["tecnologia"]["itens"][0]["preco"] == 22800


def test_preco_por_imagem_passa_por_cima_do_historico(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    svc.gerar(db, _estrutura(), tmp_path)  # cria histórico da GALLI a preço de tabela
    out = svc.levantar(db, _estrutura(estrategia="historico") | {"preco_por_imagem": 2200})
    assert out["estrategia_usada"].startswith("historico")
    assert out["fechado"]["orcamento"]["externas"]["itens"][0]["preco"] == 2200


def test_ajuste_absurdo_e_erro_de_entrada(db):
    _prep(db)
    with pytest.raises(ValueError, match="ajuste_planilha_pct"):
        svc.levantar(db, _estrutura() | {"ajuste_planilha_pct": -100})
    with pytest.raises(ValueError, match="preco_por_imagem"):
        svc.levantar(db, _estrutura() | {"preco_por_imagem": -1})


def test_servico_com_duracao_mantem_a_redacao_do_usuario(db):
    """Turtitta: 'Filme Institucional de até 2:00' — a linha do catálogo diz
    3:30 e não pode sobrescrever a duração fechada com o cliente."""
    _prep(db)
    est = _estrutura_rinno() | {"rinno_filmes": ["filme institucional de até 2:00"]}
    out = svc.levantar(db, est)
    item = out["fechado"]["orcamento"]["rinno_filmes"]["itens"][0]
    assert item["descricao"] == "Filme institucional de até 2:00"
    assert item["preco"] == 18000  # mas o preço é o do institucional


# ---------- preço informado por item ----------


def test_item_com_preco_fechado_usa_o_valor_dito(db):
    """Turtitta: institucional de até 2:00 por 15.000 — a tabela diz 18.000 para
    o institucional, e a duração é outra. O número vem de quem negociou."""
    _prep(db)
    est = _estrutura_rinno() | {
        "rinno_filmes": [{"descricao": "Filme institucional de até 2:00", "preco": 15000},
                         "Filme corretor"],
        "rinno_takes": [],
    }
    out = svc.levantar(db, est)
    itens = out["fechado"]["orcamento"]["rinno_filmes"]["itens"]
    assert itens[0]["descricao"] == "Filme institucional de até 2:00"
    assert itens[0]["preco"] == 15000 and itens[0]["fonte"] == "informado"
    assert itens[1]["preco"] == 10000 and itens[1]["fonte"] == "planilha:filme_produto"
    assert out["fechado"]["financeiro"]["total"] == 25000.0


def test_preco_informado_ganha_do_preco_por_imagem_e_do_ajuste(db):
    _prep(db)
    est = _estrutura() | {
        "preco_por_imagem": 2400, "ajuste_planilha_pct": 10,
        "externas": [{"descricao": "Fachada noturna", "preco": 5000}, "Piscina"],
    }
    out = svc.levantar(db, est)
    itens = out["fechado"]["orcamento"]["externas"]["itens"]
    assert itens[0]["preco"] == 5000 and itens[0]["fonte"] == "informado"
    assert itens[1]["preco"] == 2400 and itens[1]["fonte"] == "fixo_por_imagem"


def test_preco_informado_ganha_do_historico(db, tmp_path, monkeypatch):
    _prep(db)
    monkeypatch.setattr(svc, "enviar_docx", lambda caminho, chave: None)
    svc.gerar(db, _estrutura(), tmp_path)
    est = _estrutura(estrategia="historico") | {
        "externas": [{"descricao": "Fachada vista da calçada", "preco": 4200}]}
    out = svc.levantar(db, est)
    assert out["fechado"]["orcamento"]["externas"]["itens"][0]["preco"] == 4200


def test_remap_de_categoria_preserva_o_preco_informado(db):
    _prep(db)
    est = _estrutura_rinno() | {"rinno_filmes": [],
                                "filmes": [{"descricao": "Filme institucional de 2:00", "preco": 15000}]}
    out = svc.levantar(db, est)
    assert out["fechado"]["orcamento"]["rinno_filmes"]["itens"][0]["preco"] == 15000


def test_preco_informado_negativo_e_erro(db):
    _prep(db)
    with pytest.raises(ValueError, match="preço informado inválido"):
        svc.levantar(db, _estrutura() | {"externas": [{"descricao": "Fachada", "preco": -1}]})
