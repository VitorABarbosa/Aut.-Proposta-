import pytest

from app.storage import r2

ENVS = {
    "R2_ACCOUNT_ID": "conta123",
    "R2_ACCESS_KEY_ID": "chave",
    "R2_SECRET_ACCESS_KEY": "segredo",
    "R2_BUCKET": "propostas",
}


def _limpa_envs(monkeypatch):
    for k in list(ENVS) + ["R2_PUBLIC_BASE_URL"]:
        monkeypatch.delenv(k, raising=False)


def test_sem_credenciais_nao_configurado(monkeypatch):
    _limpa_envs(monkeypatch)
    assert r2.r2_configurado() is False


def test_sem_credenciais_enviar_devolve_none(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"conteudo")
    assert r2.enviar_docx(arq, "propostas/p.docx") is None


def test_upload_ok_devolve_url_publica(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://arquivos.flyingstudio.com.br")

    chamadas = {}

    class FakeS3:
        def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
            chamadas.update(Filename=Filename, Bucket=Bucket, Key=Key)

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())

    arq = tmp_path / "p.docx"
    arq.write_bytes(b"conteudo")
    url = r2.enviar_docx(arq, "propostas/proposta_1.docx")

    assert url == "https://arquivos.flyingstudio.com.br/propostas/proposta_1.docx"
    assert chamadas["Bucket"] == "propostas"
    assert chamadas["Key"] == "propostas/proposta_1.docx"


def test_upload_sem_base_url_usa_endpoint_r2(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)

    class FakeS3:
        def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
            pass

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    url = r2.enviar_docx(arq, "propostas/p.docx")
    assert url == "https://conta123.r2.cloudflarestorage.com/propostas/propostas/p.docx"


def test_falha_de_upload_devolve_none(monkeypatch, tmp_path):
    _limpa_envs(monkeypatch)
    for k, v in ENVS.items():
        monkeypatch.setenv(k, v)

    class FakeS3:
        def upload_file(self, *a, **kw):
            raise RuntimeError("rede caiu")

    monkeypatch.setattr(r2, "_cliente_s3", lambda: FakeS3())
    arq = tmp_path / "p.docx"
    arq.write_bytes(b"x")
    assert r2.enviar_docx(arq, "propostas/p.docx") is None
