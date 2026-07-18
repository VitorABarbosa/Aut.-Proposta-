# Automação de Proposta — Plano 1: Núcleo Determinístico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o motor de precificação determinístico do serviço de proposta — classificação de itens, levantamento por planilha, e descontos — totalmente testado com pytest, sem depender de banco, rede ou LLM.

**Architecture:** Serviço Python (FastAPI virá no Plano 3). Este plano entrega só o pacote `app/dominio/`: funções puras que recebem descrições de itens e devolvem um orçamento com preços vindos de uma tabela versionada (JSON), somas por categoria e aplicação de descontos. O LLM nunca produz números — este núcleo é a fonte da verdade financeira.

**Tech Stack:** Python 3.12, pytest, dataclasses. Sem dependências externas neste plano.

## Roadmap dos planos (contexto)

Este é o Plano 1 de 4. Cada plano entrega software funcional e testável:
1. **Núcleo determinístico** (este) — precificação/soma/descontos.
2. **Persistência NEON + histórico** — schema, repos, seed, 2º levantamento.
3. **Documento + IA + API** — docx timbrado, R2, OpenAI + fallback, rotas FastAPI.
4. **UI no hub** — componente Next.js (ChatPanel + PreviewPanel).

## Global Constraints

- Python **3.12+**.
- Todo dinheiro é `int` (reais inteiros) na tabela; descontos podem gerar `float`, sempre arredondado a 2 casas na saída.
- Nenhum módulo de `app/dominio/` pode importar rede, banco ou SDK de LLM.
- Categorias base fixas: `("externas", "internas", "plantas")`.
- Código e comentários em português, seguindo o estilo do repositório antigo.
- Fonte de referência a portar: `Aut_proposta_old/Flying-studio-proposta/flying/{precos,orcamento}.py` e `data/precos_planilha.json`.

---

### Task 1: Scaffold do projeto Python

**Files:**
- Create: `aut-proposta/pyproject.toml`
- Create: `aut-proposta/README.md`
- Create: `aut-proposta/app/__init__.py`
- Create: `aut-proposta/app/dominio/__init__.py`
- Create: `aut-proposta/tests/__init__.py`
- Create: `aut-proposta/tests/test_smoke.py`

**Interfaces:**
- Consumes: nada.
- Produces: pacote importável `app` e `app.dominio`; comando `pytest` funcional a partir de `aut-proposta/`.

- [ ] **Step 1: Criar `pyproject.toml`**

```toml
[project]
name = "aut-proposta"
version = "0.1.0"
description = "Automação de Proposta Flying Studio — serviço de precificação e geração de propostas"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Criar arquivos de pacote vazios**

`aut-proposta/app/__init__.py`, `aut-proposta/app/dominio/__init__.py` e `aut-proposta/tests/__init__.py` — todos vazios (conteúdo: uma linha em branco).

Criar `aut-proposta/README.md`:

```markdown
# aut-proposta

Serviço da Automação de Proposta Flying Studio (FastAPI + NEON + Cloudflare R2).
Ver `../docs/superpowers/specs/2026-07-18-automacao-proposta-design.md`.

## Rodar testes

```bash
cd aut-proposta
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 3: Escrever o teste de smoke**

`aut-proposta/tests/test_smoke.py`:

```python
def test_importa_pacote_dominio():
    import app.dominio  # noqa: F401
```

- [ ] **Step 4: Instalar e rodar o teste**

Run (a partir de `aut-proposta/`):
```bash
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/
git commit -m "chore(proposta): scaffold do serviço Python + pytest"
```

---

### Task 2: Normalização de texto (`dominio/texto.py`)

**Files:**
- Create: `aut-proposta/app/dominio/texto.py`
- Test: `aut-proposta/tests/dominio/__init__.py`, `aut-proposta/tests/dominio/test_texto.py`

**Interfaces:**
- Consumes: nada.
- Produces: `normalizar(s: str) -> str` — minúsculas, sem acento, espaços colapsados. Usada por `precos` e `orcamento`.

- [ ] **Step 1: Escrever o teste que falha**

`aut-proposta/tests/dominio/__init__.py` vazio. `aut-proposta/tests/dominio/test_texto.py`:

```python
from app.dominio.texto import normalizar


def test_remove_acento_e_baixa_caixa():
    assert normalizar("Fachada Vista da Calçada") == "fachada vista da calcada"


def test_colapsa_espacos_e_apara():
    assert normalizar("  Planta   Térreo  ") == "planta terreo"


def test_string_vazia():
    assert normalizar("") == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/dominio/test_texto.py -v`
Expected: FAIL (ModuleNotFoundError: app.dominio.texto).

- [ ] **Step 3: Implementar**

`aut-proposta/app/dominio/texto.py`:

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/dominio/test_texto.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/dominio/texto.py aut-proposta/tests/dominio/
git commit -m "feat(proposta): normalização de texto do domínio"
```

---

### Task 3: Tabela de preços e classificação (`dominio/precos.py`)

**Files:**
- Create: `aut-proposta/app/dados/precos_planilha.json` (copiado do repo antigo)
- Create: `aut-proposta/app/dominio/precos.py`
- Test: `aut-proposta/tests/dominio/test_precos.py`

**Interfaces:**
- Consumes: `app.dominio.texto.normalizar`.
- Produces:
  - `class TabelaPrecos` com `__init__(self, dados: dict | None = None)` (se `dados=None`, carrega o JSON padrão de `app/dados/precos_planilha.json`).
  - `TabelaPrecos.classificar(descricao: str, categoria: str) -> dict` retornando `{"chave": str, "descricao_padrao": str, "preco": int}`. `categoria` ∈ `{"externas","internas","plantas"}`; outra levanta `ValueError`.

- [ ] **Step 1: Copiar o JSON da tabela de preços**

Run (a partir de `aut-proposta/`):
```bash
mkdir -p app/dados
cp ../Aut_proposta_old/Flying-studio-proposta/data/precos_planilha.json app/dados/precos_planilha.json
```
Expected: arquivo `app/dados/precos_planilha.json` existe (~vários KB).

- [ ] **Step 2: Escrever os testes que falham**

`aut-proposta/tests/dominio/test_precos.py`:

```python
import pytest

from app.dominio.precos import TabelaPrecos

# Tabela mínima em memória, espelhando a estrutura do JSON real.
DADOS = {
    "externas": {
        "_default": 1900,
        "_descricao_padrao": "Perspectiva Externa",
        "tabela": [
            {"chave": "fachada", "descricao": "Perspectiva Fachada / Voo",
             "preco": 3000, "padroes": [r"\bfachada\b", "voo de passaro"]},
            {"chave": "externa_diversa", "descricao": "Perspectiva Externa",
             "preco": 1900, "padroes": [".*"]},
        ],
    },
    "internas": {
        "_default": 1750, "_descricao_padrao": "Perspectiva Interna",
        "tabela": [{"chave": "interna_diversa", "descricao": "Perspectiva Interna",
                    "preco": 1750, "padroes": [".*"]}],
    },
    "plantas": {
        "_default": 1200, "_descricao_padrao": "Planta Humanizada",
        "tabela": [
            {"chave": "implantacao", "descricao": "Planta Humanizada Implantação",
             "preco": 3000, "padroes": ["implantacao", "terreo"]},
            {"chave": "planta_tipo", "descricao": "Planta Humanizada Tipo",
             "preco": 1200, "padroes": [".*"]},
        ],
    },
}


def tabela():
    return TabelaPrecos(DADOS)


def test_classifica_fachada_como_3000():
    r = tabela().classificar("Fachada vista da calçada", "externas")
    assert r["chave"] == "fachada"
    assert r["preco"] == 3000


def test_externa_generica_cai_no_default():
    r = tabela().classificar("Perspectiva Jardim", "externas")
    assert r["preco"] == 1900


def test_planta_terreo_vira_implantacao():
    r = tabela().classificar("Planta Térreo", "plantas")
    assert r["preco"] == 3000


def test_categoria_invalida_levanta_erro():
    with pytest.raises(ValueError):
        tabela().classificar("qualquer", "filmes")


def test_carrega_json_padrao_quando_sem_dados():
    # Não passa 'dados' -> deve carregar o JSON real do disco sem erro.
    t = TabelaPrecos()
    r = t.classificar("Perspectiva Sala", "internas")
    assert isinstance(r["preco"], int)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/dominio/test_precos.py -v`
Expected: FAIL (ModuleNotFoundError: app.dominio.precos).

- [ ] **Step 4: Implementar**

`aut-proposta/app/dominio/precos.py`:

```python
"""Carrega a tabela de preços e classifica descrições livres de itens.

Você passa a descrição de uma imagem (ex.: "Fachada vista da calçada") e a
categoria geral ("externas"/"internas"/"plantas"); a função descobre qual
linha da tabela aplicar via regex e devolve chave, descrição padrão e preço.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.dominio.texto import normalizar

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"
PRECOS_PATH = DADOS_DIR / "precos_planilha.json"

CATEGORIAS_VALIDAS = ("externas", "internas", "plantas")


class TabelaPrecos:
    """Wrapper sobre o JSON da planilha com helper de classificação."""

    def __init__(self, dados: dict[str, Any] | None = None) -> None:
        if dados is None:
            with open(PRECOS_PATH, encoding="utf-8") as f:
                dados = json.load(f)
        self.dados = dados

    def classificar(self, descricao: str, categoria: str) -> dict[str, Any]:
        if categoria not in CATEGORIAS_VALIDAS:
            raise ValueError(f"Categoria inválida: {categoria}")

        bloco = self.dados[categoria]
        alvo = normalizar(descricao)

        for linha in bloco["tabela"]:
            for padrao in linha["padroes"]:
                if re.search(padrao, alvo):
                    return {
                        "chave": linha["chave"],
                        "descricao_padrao": linha["descricao"],
                        "preco": linha["preco"],
                    }

        return {
            "chave": "default",
            "descricao_padrao": bloco["_descricao_padrao"],
            "preco": bloco["_default"],
        }
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/dominio/test_precos.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add aut-proposta/app/dados/precos_planilha.json aut-proposta/app/dominio/precos.py aut-proposta/tests/dominio/test_precos.py
git commit -m "feat(proposta): tabela de preços + classificação por regex"
```

---

### Task 4: Levantamento por planilha (`dominio/orcamento.py`)

**Files:**
- Create: `aut-proposta/app/dominio/orcamento.py`
- Test: `aut-proposta/tests/dominio/test_orcamento.py`

**Interfaces:**
- Consumes: `TabelaPrecos`, `normalizar`.
- Produces:
  - `@dataclass ItemOrcado(descricao: str, descricao_normalizada: str, preco: int, fonte: str)` com `.to_dict()`.
  - `@dataclass CategoriaOrcada(nome: str, itens: list[ItemOrcado])` com props `.total: int`, `.qtd: int`, e `.to_dict()`.
  - `@dataclass Orcamento(estrategia: str, externas, internas, plantas)` com props `.subtotal: int`, `.total_imagens: int`, e `.to_dict()`.
  - `orcar_pela_planilha(descricoes: dict[str, list[str]], tabela: TabelaPrecos | None = None) -> Orcamento`. `descricoes` mapeia categoria → lista de descrições.

- [ ] **Step 1: Escrever os testes que falham**

`aut-proposta/tests/dominio/test_orcamento.py`:

```python
from app.dominio.orcamento import orcar_pela_planilha
from app.dominio.precos import TabelaPrecos
from tests.dominio.test_precos import DADOS


def tabela():
    return TabelaPrecos(DADOS)


def test_soma_por_categoria_e_subtotal():
    desc = {
        "externas": ["Fachada vista da calçada", "Jardim"],  # 3000 + 1900
        "internas": ["Academia", "Sauna"],                    # 1750 + 1750
        "plantas": ["Térreo"],                                # 3000
    }
    orc = orcar_pela_planilha(desc, tabela())
    assert orc.externas.total == 4900
    assert orc.internas.total == 3500
    assert orc.plantas.total == 3000
    assert orc.subtotal == 11400
    assert orc.total_imagens == 5


def test_prefixa_descricao_padrao():
    orc = orcar_pela_planilha({"internas": ["Academia"]}, tabela())
    assert orc.internas.itens[0].descricao_normalizada == "Perspectiva Academia"


def test_nao_duplica_prefixo_quando_usuario_ja_escreveu():
    orc = orcar_pela_planilha({"internas": ["Perspectiva Sauna"]}, tabela())
    assert orc.internas.itens[0].descricao_normalizada == "Perspectiva Sauna"


def test_categoria_ausente_fica_vazia():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    assert orc.externas.qtd == 0
    assert orc.plantas.qtd == 0


def test_to_dict_tem_estrutura_esperada():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, tabela())
    d = orc.to_dict()
    assert d["estrategia"] == "planilha"
    assert d["subtotal"] == 1750
    assert d["internas"]["itens"][0]["preco"] == 1750
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/dominio/test_orcamento.py -v`
Expected: FAIL (ModuleNotFoundError: app.dominio.orcamento).

- [ ] **Step 3: Implementar**

`aut-proposta/app/dominio/orcamento.py`:

```python
"""Levantamento de orçamento pela tabela padrão (planilha).

Classifica cada descrição, aplica o preço da tabela e formata a descrição no
padrão de escrita do Flying Studio. Soma por categoria e no total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dominio.precos import TabelaPrecos
from app.dominio.texto import normalizar

CATEGORIAS = ("externas", "internas", "plantas")
PREFIXOS = {
    "externas": "Perspectiva ",
    "internas": "Perspectiva ",
    "plantas": "Planta Humanizada ",
}
_PREFIXOS_JA_ESCRITOS = {
    "externas": ("perspectiva", "estudo de fachada", "estudo cromatic"),
    "internas": ("perspectiva",),
    "plantas": ("planta",),
}


@dataclass
class ItemOrcado:
    descricao: str
    descricao_normalizada: str
    preco: int
    fonte: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "descricao": self.descricao_normalizada,
            "preco": self.preco,
            "fonte": self.fonte,
        }


@dataclass
class CategoriaOrcada:
    nome: str
    itens: list[ItemOrcado] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(i.preco for i in self.itens)

    @property
    def qtd(self) -> int:
        return len(self.itens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "qtd": self.qtd,
            "total": self.total,
            "itens": [i.to_dict() for i in self.itens],
        }


@dataclass
class Orcamento:
    estrategia: str
    externas: CategoriaOrcada
    internas: CategoriaOrcada
    plantas: CategoriaOrcada

    @property
    def subtotal(self) -> int:
        return self.externas.total + self.internas.total + self.plantas.total

    @property
    def total_imagens(self) -> int:
        return self.externas.qtd + self.internas.qtd + self.plantas.qtd

    def to_dict(self) -> dict[str, Any]:
        return {
            "estrategia": self.estrategia,
            "subtotal": self.subtotal,
            "total_imagens": self.total_imagens,
            "externas": self.externas.to_dict(),
            "internas": self.internas.to_dict(),
            "plantas": self.plantas.to_dict(),
        }


def _formata_descricao(desc_usuario: str, categoria: str) -> str:
    """Aplica o jeito de escrever do Flying Studio.

    Se o usuário já começou com 'Perspectiva'/'Planta'/etc., mantém (só sobe a
    inicial). Senão, prefixa com o padrão da categoria.
    """
    desc = desc_usuario.strip()
    norm = normalizar(desc)
    if any(norm.startswith(p) for p in _PREFIXOS_JA_ESCRITOS.get(categoria, ())):
        return desc[:1].upper() + desc[1:] if desc else desc
    return PREFIXOS[categoria] + desc


def orcar_pela_planilha(
    descricoes: dict[str, list[str]],
    tabela: TabelaPrecos | None = None,
) -> Orcamento:
    tabela = tabela or TabelaPrecos()
    cats: dict[str, CategoriaOrcada] = {c: CategoriaOrcada(nome=c) for c in CATEGORIAS}

    for cat in CATEGORIAS:
        for desc in descricoes.get(cat, []):
            classif = tabela.classificar(desc, cat)
            cats[cat].itens.append(
                ItemOrcado(
                    descricao=desc,
                    descricao_normalizada=_formata_descricao(desc, cat),
                    preco=classif["preco"],
                    fonte=f"planilha:{classif['chave']}",
                )
            )

    return Orcamento(
        estrategia="planilha",
        externas=cats["externas"],
        internas=cats["internas"],
        plantas=cats["plantas"],
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/dominio/test_orcamento.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/dominio/orcamento.py aut-proposta/tests/dominio/test_orcamento.py
git commit -m "feat(proposta): levantamento de orçamento pela planilha"
```

---

### Task 5: Descontos (`dominio/descontos.py`)

**Files:**
- Create: `aut-proposta/app/dominio/descontos.py`
- Test: `aut-proposta/tests/dominio/test_descontos.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `@dataclass Desconto(tipo: str, valor: float, rotulo: str = "")`. `tipo` ∈ `{"percentual","valor"}`; outro levanta `ValueError` ao aplicar. `valor` de percentual é 0–100.
  - `aplicar_desconto(subtotal: int, desconto: Desconto | None) -> dict` retornando `{"subtotal": int, "desconto_pct": float, "desconto_valor": float, "total": float, "rotulo": str}`. `desconto=None` → sem desconto. `desconto_valor` e `total` arredondados a 2 casas; nunca deixa total negativo (piso 0).

- [ ] **Step 1: Escrever os testes que falham**

`aut-proposta/tests/dominio/test_descontos.py`:

```python
import pytest

from app.dominio.descontos import Desconto, aplicar_desconto


def test_sem_desconto():
    r = aplicar_desconto(10000, None)
    assert r["desconto_valor"] == 0
    assert r["total"] == 10000


def test_desconto_percentual():
    r = aplicar_desconto(23450, Desconto("percentual", 12, "12% Parceria"))
    assert r["desconto_valor"] == 2814.0
    assert r["total"] == 20636.0
    assert r["desconto_pct"] == 12
    assert r["rotulo"] == "12% Parceria"


def test_desconto_valor_fixo():
    r = aplicar_desconto(10000, Desconto("valor", 1500))
    assert r["desconto_valor"] == 1500
    assert r["total"] == 8500


def test_desconto_nao_deixa_total_negativo():
    r = aplicar_desconto(1000, Desconto("valor", 5000))
    assert r["total"] == 0


def test_tipo_invalido_levanta_erro():
    with pytest.raises(ValueError):
        aplicar_desconto(1000, Desconto("bonus", 10))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/dominio/test_descontos.py -v`
Expected: FAIL (ModuleNotFoundError: app.dominio.descontos).

- [ ] **Step 3: Implementar**

`aut-proposta/app/dominio/descontos.py`:

```python
"""Aplicação de descontos sobre o subtotal de um orçamento.

Suporta desconto percentual (0-100) e valor fixo em reais. O cálculo é
determinístico e nunca deixa o total ficar negativo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TIPOS_VALIDOS = ("percentual", "valor")


@dataclass
class Desconto:
    tipo: str
    valor: float
    rotulo: str = ""


def aplicar_desconto(subtotal: int, desconto: Desconto | None) -> dict[str, Any]:
    if desconto is None:
        return {
            "subtotal": subtotal,
            "desconto_pct": 0.0,
            "desconto_valor": 0.0,
            "total": float(subtotal),
            "rotulo": "",
        }

    if desconto.tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo de desconto inválido: {desconto.tipo}")

    if desconto.tipo == "percentual":
        desconto_pct = float(desconto.valor)
        desconto_valor = subtotal * (desconto_pct / 100.0)
    else:  # valor
        desconto_valor = float(desconto.valor)
        desconto_pct = (desconto_valor / subtotal * 100.0) if subtotal else 0.0

    total = max(0.0, subtotal - desconto_valor)

    return {
        "subtotal": subtotal,
        "desconto_pct": round(desconto_pct, 2),
        "desconto_valor": round(desconto_valor, 2),
        "total": round(total, 2),
        "rotulo": desconto.rotulo,
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/dominio/test_descontos.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/dominio/descontos.py aut-proposta/tests/dominio/test_descontos.py
git commit -m "feat(proposta): aplicação de descontos"
```

---

### Task 6: Fechamento do orçamento + teste de caso real

**Files:**
- Modify: `aut-proposta/app/dominio/orcamento.py` (adicionar `fechar_orcamento`)
- Test: `aut-proposta/tests/dominio/test_fechamento.py`

**Interfaces:**
- Consumes: `Orcamento`, `Desconto`, `aplicar_desconto`.
- Produces: `fechar_orcamento(orcamento: Orcamento, desconto: Desconto | None = None) -> dict` — junta o `orcamento.to_dict()` com o resultado de `aplicar_desconto(orcamento.subtotal, desconto)` numa única estrutura `{"orcamento": {...}, "financeiro": {...}}`.

- [ ] **Step 1: Escrever o teste que falha (caso real GALLI)**

`aut-proposta/tests/dominio/test_fechamento.py`:

```python
from app.dominio.descontos import Desconto
from app.dominio.orcamento import fechar_orcamento, orcar_pela_planilha
from app.dominio.precos import TabelaPrecos

# Caso real (proposta GALLI/Aiach): usa a tabela de preços REAL do JSON.
# 9 externas (2 fachadas a 3000 + 7 diversas a 1900) = 19300
# 5 internas a 1750 = 8750
# 4 plantas (3 implantação a 3000 + 1 tipo a 1200) = 10200
# subtotal = 38250 ; com 12% de desconto -> 33660
DESCRICOES = {
    "externas": [
        "Fachada vista da calçada", "Jardim", "Quadra de areia", "Piscina",
        "Dec c Jacuzzi", "Playground", "Gourmet churrasqueira",
        "Terraço rooftop", "Fachada Bird's View",
    ],
    "internas": ["Bicicletário", "Academia", "Sauna", "Brinquedoteca", "Salão de Festas"],
    "plantas": [
        "Implantação Térreo", "Implantação Mezanino lazer",
        "Implantação rooftop", "Apartamento Tipo",
    ],
}


def test_fechamento_caso_galli_com_desconto():
    orc = orcar_pela_planilha(DESCRICOES, TabelaPrecos())
    assert orc.subtotal == 38250

    fechado = fechar_orcamento(orc, Desconto("percentual", 12, "12% de Desconto de Parceria"))
    assert fechado["orcamento"]["subtotal"] == 38250
    assert fechado["financeiro"]["desconto_valor"] == 4590.0
    assert fechado["financeiro"]["total"] == 33660.0


def test_fechamento_sem_desconto():
    orc = orcar_pela_planilha({"internas": ["Sala"]}, TabelaPrecos())
    fechado = fechar_orcamento(orc)
    assert fechado["financeiro"]["total"] == float(orc.subtotal)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/dominio/test_fechamento.py -v`
Expected: FAIL (ImportError: cannot import name 'fechar_orcamento').

Nota: se o `subtotal` real divergir de 38250, é sinal de que a tabela real classifica algum item diferente do esperado — ajuste as descrições do teste para casar as regex reais (ex.: "Fachada Bird's View" precisa casar o padrão de fachada/voo) antes de mexer no código.

- [ ] **Step 3: Implementar `fechar_orcamento`**

Adicionar ao final de `aut-proposta/app/dominio/orcamento.py`:

```python
from app.dominio.descontos import Desconto, aplicar_desconto


def fechar_orcamento(orcamento: Orcamento, desconto: "Desconto | None" = None) -> dict[str, Any]:
    """Junta o orçamento e o cálculo financeiro (com desconto) numa estrutura."""
    return {
        "orcamento": orcamento.to_dict(),
        "financeiro": aplicar_desconto(orcamento.subtotal, desconto),
    }
```

- [ ] **Step 4: Rodar e ver passar (toda a suíte)**

Run: `pytest -v`
Expected: PASS (todos os testes das Tasks 1–6).

- [ ] **Step 5: Commit**

```bash
git add aut-proposta/app/dominio/orcamento.py aut-proposta/tests/dominio/test_fechamento.py
git commit -m "feat(proposta): fechamento do orçamento com desconto + caso real GALLI"
```

---

## Self-Review

**Cobertura do spec (Seções 2 e 4 do design que este plano cobre):**
- Classificação/precificação por regex (Seção 4 `dominio/precos`) → Task 3. ✔
- Levantamento pela planilha (Seção 4 `dominio/orcamento`) → Task 4. ✔
- Descontos %/valor fixo (Seção 4 `dominio/descontos`) → Task 5. ✔
- "Código calcula soma/preços/descontos" (princípio-chave) → Tasks 4–6, sem rede/LLM. ✔
- Testes com casos reais (Seção 8) → Task 6 (GALLI). ✔
- **Fora deste plano (intencional):** histórico/2º levantamento, NEON, docx, R2, IA, API, UI → Planos 2–4.

**Placeholders:** nenhum "TBD"/"handle edge cases"; todo código está presente.

**Consistência de tipos:** `TabelaPrecos.classificar` → `{"chave","descricao_padrao","preco"}` usado igual em `orcamento`. `normalizar` (nome único, não `_norm`) usado em `texto`, `precos`, `orcamento`. `aplicar_desconto(subtotal, desconto)` assinatura idêntica em Tasks 5 e 6. `Desconto(tipo, valor, rotulo)` consistente.

**Nota de dependência:** o Task 6 importa `descontos` dentro de `orcamento.py`. Como `descontos.py` não importa `orcamento`, não há import circular.
