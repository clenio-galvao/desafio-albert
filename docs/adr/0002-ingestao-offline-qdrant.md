# ADR 0002 — Ingestão offline idempotente e Qdrant

Status: aceito.

## Contexto

Os PDFs são privados, embeddings consomem uma cota compartilhada e ambientes
gratuitos podem sofrer cold starts ou não possuir disco persistente. Recriar o
índice ao iniciar a API seria lento, caro e frágil.

## Decisão

Separar ingestão e consulta. Scripts explícitos baixam os documentos e executam
extração, normalização, chunking e embeddings antes do deploy. Cada chunk
recebe ID e hash determinísticos; hashes já existentes são ignorados.

Persistir vetores e payloads no Qdrant Cloud, com índices para `source`, `page`
e `content_hash`. PDFs e índices locais permanecem fora do Git.

## Consequências

- Inicializar a API não gera embeddings nem depende dos PDFs.
- Reingestões sem alteração não consomem novamente a cota.
- O índice sobrevive a reinícios do serviço.
- Mudanças no algoritmo de chunking ou no modelo podem exigir nova coleção ou
  migração explícita.
- A disponibilidade da consulta depende do Qdrant externo.
