# Desafio Albert — Chatbot RAG

API de chatbot em construção com FastAPI, arquitetura hexagonal, recuperação
de conhecimento das apostilas de saúde mental e respostas em streaming.

O planejamento completo e o acompanhamento da implementação estão em
[ROADMAP.md](ROADMAP.md).

## Estado atual

O projeto está na etapa inicial de infraestrutura e qualidade. A documentação
de execução, arquitetura, decisões, testes, deploy e uso de IA será ampliada
junto com os próximos commits.

## Desenvolvimento

Requer Python 3.12 ou superior.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy
```

Para iniciar a API:

```bash
uvicorn chatbot.main:app --reload
```

O health check inicial estará disponível em
`http://localhost:8000/health/live`.

## Preparação da base

O download e a ingestão são comandos explícitos: iniciar a API não consome a
cota dos modelos.

```bash
python scripts/download_documents.py
python scripts/ingest.py
```

O primeiro comando salva as quatro apostilas em `data/documents`, diretório
ignorado pelo Git. O segundo cria embeddings apenas para chunks ainda ausentes
no Qdrant e imprime um resumo da operação. Revise as variáveis do `.env` antes
de executá-lo, pois essa etapa realiza chamadas cobradas ao gateway.

## Segurança

Copie `.env.example` para `.env` e preencha as credenciais apenas localmente.
Nunca faça commit de chaves, apostilas em PDF ou índices gerados.
