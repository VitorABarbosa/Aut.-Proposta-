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
