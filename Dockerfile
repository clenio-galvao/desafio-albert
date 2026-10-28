FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system chatbot \
    && useradd --system --gid chatbot --create-home chatbot

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER chatbot

EXPOSE 8000

CMD ["sh", "-c", "uvicorn chatbot.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
