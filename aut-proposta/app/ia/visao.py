"""Guardas de entrada das imagens (prints) mandadas no chat.

Print de celular chega em resolução cheia e vira token caro sem nenhum ganho
de leitura. Aqui a imagem passa por três filtros antes de ir para o modelo:

1. tamanho — payload acima de `MAX_BYTES` é recusado com mensagem amigável;
2. validação real — o formato vem das assinaturas do arquivo (magic bytes),
   não do mime declarado no data URL, que o cliente pode mentir;
3. downscale — largura e altura caem para `LARGURA_MAXIMA`/`ALTURA_MAXIMA` e
   a imagem é reencodada em JPEG.

O downscale limita os dois lados SEPARADAMENTE, e não o maior lado, porque
print de e-mail é alto e estreito: com um teto único de 1400px, uma captura de
1200x3000 virava 560x1400 e a letra sumia — era assim que "2º ao 13º Pavimento"
chegava ao modelo como "2º ao 3º". E não se economizava nada com isso: a API de
visão normaliza o menor lado para 768px de qualquer jeito, então as duas
versões custam os mesmos tiles. Esmagar antes era perder leitura de graça.

Sem Pillow instalado os dois primeiros filtros continuam valendo e o downscale
é pulado — a leitura funciona, só sai mais cara.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
from typing import NamedTuple

MAX_BYTES = 5 * 1024 * 1024   # por imagem, já decodificada
MAX_IMAGENS = 4               # por mensagem
LARGURA_MAXIMA = 1600         # px de largura após o downscale
ALTURA_MAXIMA = 3600          # px de altura — print alto de e-mail cabe inteiro
QUALIDADE_JPEG = 85

# Formatos que a API de visão aceita, reconhecidos pela assinatura do arquivo.
_ASSINATURAS: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

# O mime declarado é ignorado de propósito — quem decide o formato é a
# assinatura do arquivo, em `_detectar_mime`.
_RE_DATA_URL = re.compile(r"^data:(?:[\w.+-]+/[\w.+-]+)?;base64,(?P<dados>.*)$", re.DOTALL)


class ImagemInvalida(ValueError):
    """Entrada recusada pelas guardas — a mensagem é mostrada ao usuário."""


class Imagem(NamedTuple):
    url: str      # data URL já normalizado, pronto para o modelo
    mime: str
    hash: str     # sha256 do conteúdo normalizado — chave do cache de leitura


def _detectar_mime(dados: bytes) -> str | None:
    for assinatura, mime in _ASSINATURAS:
        if dados.startswith(assinatura):
            return mime
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return None


def _e_heic(dados: bytes) -> bool:
    return dados[4:8] == b"ftyp" and dados[8:12] in (
        b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


def _redimensionar(dados: bytes) -> tuple[bytes, str]:
    """Downscale + JPEG. Sem Pillow instalado devolve o original — as guardas
    de tamanho e formato já passaram, a leitura só sai mais cara.

    Com Pillow disponível, arquivo que não abre é recusado: assinatura certa e
    conteúdo quebrado é anexo inválido, não imagem para mandar ao modelo.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return dados, ""

    try:
        with Image.open(io.BytesIO(dados)) as img:
            img.seek(0)  # GIF animado: só o primeiro quadro
            img = img.convert("RGB")
            escala = min(1.0, LARGURA_MAXIMA / img.width, ALTURA_MAXIMA / img.height)
            if escala < 1.0:
                novo = (max(1, round(img.width * escala)), max(1, round(img.height * escala)))
                img = img.resize(novo, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=QUALIDADE_JPEG, optimize=True)
    except Image.DecompressionBombError:
        # Arquivo pequeno que estoura em pixels ao descompactar.
        raise ImagemInvalida(
            "Esse print tem resolução grande demais. Manda uma captura da tela "
            "em vez da imagem em resolução cheia.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImagemInvalida(
            "Não consegui abrir esse print — o arquivo parece corrompido. "
            "Tira o print de novo e manda em PNG ou JPG.") from None
    return buf.getvalue(), "image/jpeg"


def normalizar_imagem(url: str) -> Imagem:
    """Valida e encolhe um data URL de imagem. Levanta `ImagemInvalida`."""
    url = (url or "").strip()
    if not url.startswith("data:"):
        raise ImagemInvalida(
            "Só consigo ler print anexado como arquivo — link de imagem eu não abro. "
            "Cola a imagem aqui (PNG ou JPG) que eu leio.")

    m = _RE_DATA_URL.match(url)
    if not m or not m.group("dados").strip():
        raise ImagemInvalida("Não consegui ler esse anexo. Manda o print de novo, em PNG ou JPG.")

    bruto = m.group("dados").strip()
    # Cheque antes de decodificar: base64 ocupa ~4/3 do conteúdo.
    if len(bruto) * 3 // 4 > MAX_BYTES:
        raise ImagemInvalida(
            f"Esse print está grande demais (limite {MAX_BYTES // (1024 * 1024)} MB). "
            "Manda uma captura da tela em vez da foto em resolução cheia.")
    try:
        dados = base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError):
        raise ImagemInvalida(
            "Não consegui ler esse anexo. Manda o print de novo, em PNG ou JPG.") from None

    if len(dados) > MAX_BYTES:
        raise ImagemInvalida(
            f"Esse print está grande demais (limite {MAX_BYTES // (1024 * 1024)} MB). "
            "Manda uma captura da tela em vez da foto em resolução cheia.")

    mime = _detectar_mime(dados)
    if mime is None:
        if _e_heic(dados):
            raise ImagemInvalida(
                "Esse print veio em HEIC, que eu não leio. Exporta ou tira o print "
                "em PNG ou JPG e manda de novo.")
        raise ImagemInvalida(
            "Esse anexo não é uma imagem (ou está num formato que eu não leio). "
            "Manda o print em PNG, JPG, WEBP ou GIF.")

    dados, novo_mime = _redimensionar(dados)
    if novo_mime:
        mime = novo_mime
    return Imagem(
        url=f"data:{mime};base64,{base64.b64encode(dados).decode()}",
        mime=mime,
        hash=hashlib.sha256(dados).hexdigest(),
    )
