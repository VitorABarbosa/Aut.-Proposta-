"""Guardas de entrada das imagens: tamanho, formato real e downscale."""
import base64
import io

import pytest
from PIL import Image

from app.ia import visao


def _data_url(dados: bytes, mime="image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(dados).decode()}"


def _png(largura: int, altura: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _dimensoes(data_url: str) -> tuple[int, int]:
    dados = base64.b64decode(data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(dados)) as img:
        return img.size


def test_print_largo_e_reduzido_pela_largura():
    img = visao.normalizar_imagem(_data_url(_png(3200, 1600)))
    assert _dimensoes(img.url) == (visao.LARGURA_MAXIMA, visao.LARGURA_MAXIMA // 2)
    assert img.mime == "image/jpeg"
    assert img.url.startswith("data:image/jpeg;base64,")


def test_print_alto_de_email_mantem_a_largura_que_da_para_ler():
    """A régua antiga era o MAIOR lado: 1200x3000 virava 560x1400 e a letra
    miúda sumia — foi assim que "2º ao 13º Pavimento" chegou como "2º ao 3º".
    Alto e estreito tem de passar inteiro."""
    img = visao.normalizar_imagem(_data_url(_png(1200, 3000)))
    assert _dimensoes(img.url) == (1200, 3000)


def test_print_altissimo_e_reduzido_pela_altura_sem_perder_proporcao():
    img = visao.normalizar_imagem(_data_url(_png(1200, 7200)))
    largura, altura = _dimensoes(img.url)
    assert altura == visao.ALTURA_MAXIMA
    assert largura == 600  # proporção preservada


def test_print_pequeno_nao_e_esticado():
    img = visao.normalizar_imagem(_data_url(_png(600, 400)))
    assert _dimensoes(img.url) == (600, 400)


def test_mesma_imagem_tem_o_mesmo_hash():
    dados = _png(800, 600)
    assert visao.normalizar_imagem(_data_url(dados)).hash == \
           visao.normalizar_imagem(_data_url(dados)).hash
    assert visao.normalizar_imagem(_data_url(_png(801, 600))).hash != \
           visao.normalizar_imagem(_data_url(dados)).hash


def test_recusa_anexo_que_nao_e_imagem():
    """Mime declarado não vale nada — o formato vem da assinatura do arquivo."""
    with pytest.raises(visao.ImagemInvalida, match="não é uma imagem"):
        visao.normalizar_imagem(_data_url(b"%PDF-1.7 nem de longe uma imagem"))


def test_recusa_heic_com_orientacao():
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
    with pytest.raises(visao.ImagemInvalida, match="HEIC"):
        visao.normalizar_imagem(_data_url(heic, "image/heic"))


def test_recusa_acima_do_limite_de_tamanho():
    gordo = _data_url(b"\x89PNG\r\n\x1a\n" + b"\x00" * (visao.MAX_BYTES + 1))
    with pytest.raises(visao.ImagemInvalida, match="grande demais"):
        visao.normalizar_imagem(gordo)


def test_recusa_link_em_vez_de_anexo():
    """Nada de buscar URL de terceiro a mando do conteúdo do chat."""
    with pytest.raises(visao.ImagemInvalida, match="link de imagem"):
        visao.normalizar_imagem("https://exemplo.com/print.png")


def test_recusa_base64_quebrado():
    with pytest.raises(visao.ImagemInvalida, match="Não consegui ler"):
        visao.normalizar_imagem("data:image/png;base64,@@@nao-e-base64@@@")


def test_sem_pillow_guardas_continuam_valendo(monkeypatch):
    """Downscale é o único que depende de Pillow; validação nunca é pulada."""
    monkeypatch.setattr(visao, "_redimensionar", lambda dados: (dados, ""))
    img = visao.normalizar_imagem(_data_url(_png(2400, 1200)))
    assert img.mime == "image/png"
    with pytest.raises(visao.ImagemInvalida):
        visao.normalizar_imagem(_data_url(b"nada a ver"))


def test_recusa_arquivo_com_assinatura_certa_e_conteudo_quebrado():
    """Magic bytes de PNG num arquivo que o Pillow não abre não passa."""
    with pytest.raises(visao.ImagemInvalida, match="corrompido"):
        visao.normalizar_imagem(_data_url(b"\x89PNG\r\n\x1a\n" + b"lixo" * 40))


def test_recusa_bomba_de_descompressao(monkeypatch):
    """PNG pequeno no disco que estoura em pixels ao abrir."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(visao.ImagemInvalida, match="resolução grande demais"):
        visao.normalizar_imagem(_data_url(_png(2000, 2000)))
