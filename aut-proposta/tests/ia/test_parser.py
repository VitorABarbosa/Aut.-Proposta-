import pytest

from app.ia import parser


TEXTO_EXEMPLO = """Cliente: GALLI, ref Residencial Aurora, a/c Daniel Pucci
Externas: Fachada vista da calçada, Jardim
Internas: Academia; Lobby
Plantas:
- Implantação Térreo
- Apartamento Tipo
10% de desconto, preço de planilha"""


def test_parse_local_extrai_tudo():
    out = parser.parse_local(TEXTO_EXEMPLO)
    assert out["cliente"]["empresa"] == "GALLI"
    assert out["cliente"]["ref"] == "Residencial Aurora"
    assert out["cliente"]["contato"] == "Daniel Pucci"
    assert out["externas"] == ["Fachada vista da calçada", "Jardim"]
    assert out["internas"] == ["Academia", "Lobby"]
    assert out["plantas"] == ["Implantação Térreo", "Apartamento Tipo"]
    assert out["desconto_pct"] == 10.0
    assert out["estrategia"] == "planilha"
    assert out["_origem"] == "local"


def test_parse_local_estrategia_historico():
    out = parser.parse_local("cliente BRNPAR, mesma base do projeto anterior. Internas: Academia")
    assert out["estrategia"] == "historico"


def test_parse_local_cliente_caps_sem_marcador():
    out = parser.parse_local("GALLI Residencial Aurora\nExternas: Fachada")
    assert out["cliente"]["empresa"] == "GALLI"
    assert any("assumi" in a for a in out["_avisos"])


def test_parse_local_vazio_avisa():
    out = parser.parse_local("")
    assert out["cliente"]["empresa"] == "CLIENTE"
    assert out["_avisos"]


def test_parse_usa_openai_quando_disponivel(monkeypatch):
    monkeypatch.setattr(parser, "_chamar_openai", lambda texto, categorias=None: {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "Daniel"},
        "externas": ["Fachada"], "internas": [], "plantas": [],
        "desconto_pct": 10, "estrategia": "planilha",
    })
    out = parser.parse("qualquer texto")
    assert out["_origem"] == "openai"
    assert out["cliente"]["empresa"] == "GALLI"
    # Defaults preenchidos mesmo quando o modelo omite chaves.
    assert out["mostrar_precos_individuais"] is False
    assert out["desconto_label"] is None


def test_parse_cai_para_local_quando_openai_falha(monkeypatch):
    def _explode(texto, categorias=None):
        raise RuntimeError("api fora")
    monkeypatch.setattr(parser, "_chamar_openai", _explode)
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "local"
    assert out["cliente"]["empresa"] == "GALLI"
    assert any("OpenAI indisponível" in a for a in out["_avisos"])


def test_parse_openai_complementado_pelo_local(monkeypatch):
    # Modelo devolveu só externas; local completa internas/plantas.
    monkeypatch.setattr(parser, "_chamar_openai", lambda texto, categorias=None: {
        "cliente": {"empresa": "GALLI", "ref": "Aurora", "contato": "—"},
        "externas": ["Fachada vista da calçada"], "internas": [], "plantas": [],
    })
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "openai"
    assert out["internas"] == ["Academia", "Lobby"]


def test_parse_sem_chave_usa_local(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = parser.parse(TEXTO_EXEMPLO)
    assert out["_origem"] == "local"


def test_parse_local_filtra_metadata_em_linha_unica():
    # Seção de uma linha só (branch de split por vírgula) também deve filtrar
    # metadata de desconto/estratégia, não só o branch multilinha.
    texto = "Cliente: GALLI\nPlantas: Apartamento Tipo, 10% de desconto, preço de planilha"
    out = parser.parse_local(texto)
    assert out["plantas"] == ["Apartamento Tipo"]
    assert out["desconto_pct"] == 10.0
    assert out["estrategia"] == "planilha"


def test_parse_local_reconhece_cabecalho_filmes_com_categorias_extras():
    texto = "Cliente: GALLI\nFilmes: Filme institucional 60s\nTour Virtual: Render sala"
    out = parser.parse_local(
        texto, categorias=["externas", "internas", "plantas", "filmes", "tour_virtual"]
    )
    assert out["filmes"] == ["Filme institucional 60s"]
    assert out["tour_virtual"] == ["Render sala"]


def test_parse_local_filtra_metadata_historico_sem_acento_multilinha():
    # Regex de filtro tinha "histórico" duplicado e sem a forma sem acento.
    texto = (
        "Cliente: GALLI\n"
        "Plantas:\n"
        "- Implantação Térreo\n"
        "- Apartamento Tipo\n"
        "usar historico do cliente"
    )
    out = parser.parse_local(texto)
    assert out["plantas"] == ["Implantação Térreo", "Apartamento Tipo"]
    assert out["estrategia"] == "historico"
