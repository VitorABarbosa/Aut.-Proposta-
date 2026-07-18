"""Normalização de texto para casar descrições livres com padrões de preço."""
from __future__ import annotations

import re
import unicodedata


def normalizar(s: str) -> str:
    """Minúsculas, sem acento, espaços únicos e aparados."""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s
