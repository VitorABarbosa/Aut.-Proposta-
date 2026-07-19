FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/aut-proposta

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
