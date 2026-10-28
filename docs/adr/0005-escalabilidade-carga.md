# ADR 0005 — Entrega concorrente, teste de carga e scale-out

Status: aceito.

## Contexto

Vários usuários podem enviar perguntas ao mesmo tempo. Cada uma abre um
Server-Sent Event e permanece aberta até o modelo terminar. A instância atual
é um único processo no Render Free, com sessões em memória e cota compartilhada
do gateway. Precisamos medir o que a API aguenta e saber o que fazer se o
resultado não for aceitável, sem gastar o orçamento em um teste contra o
ambiente publicado.

## Decisão

Tratar cada `POST /v1/chat/stream` como uma conexão independente. O event loop
do Uvicorn multiplexa os streams; não existe fila global de respostas. O
histórico continua local ao processo.

Medir a aplicação com dublês de LLM e retriever (`build_load_container` e
`python scripts/load_test.py`). O perfil publicado fica limitado a no máximo
cinco requisições reais.

Recusar novos streams com HTTP 429 quando `MAX_CONCURRENT_STREAMS` está
esgotado, e encerrar gerações lentas com timeout (`STREAM_TIMEOUT_SECONDS`)
antes de o SSE ficar aberto indefinidamente.

Se a carga local for insatisfatória ou se houver várias réplicas, a ordem de
correção é:

1. Event loop da API — reduzir trabalho síncrono e manter o limite 429.
2. Qdrant — índices e `top_k` já calibrados; só então cluster/plano pago.
3. Embedding da consulta — cache de perguntas repetidas.
4. Gateway do LLM — teto de streams e, se preciso, fila curta.
5. Sessão compartilhada — Redis via `SessionRepositoryPort`.
6. Capacidade — `WEB_CONCURRENCY` ou plano maior **depois** do Redis.

## Cenário-alvo (local, fakes)

- 25 usuários simultâneos e 100 streams.
- Tempo até o primeiro token p95 inferior a 500 ms.
- Taxa de erro inferior a 1%.
- Pelo menos 99% dos streams com `event: done`.

## Relatório

Medição local em 2026-10-28, `python scripts/load_test.py --users 25 --requests 100`,
com LLM e retriever fake:

- 100/100 streams com HTTP 200 e `event: done`;
- taxa de erro 0%;
- primeiro token p50 72 ms e p95 90 ms;
- duração p95 91 ms.

A API assíncrona aguenta o cenário-alvo. O gargalo de produção continua sendo
o gateway (embedding + LLM) e a sessão em memória, não o FastAPI. O perfil
publicado (`--target`) limita-se a cinco requisições e não deve ser usado como
teste de carga.

## Consequências

- Dá para explicar como N usuários recebem tokens ao mesmo tempo.
- A cota do desafio não é gasta para descobrir se o FastAPI aguenta.
- 429 e timeout protegem o processo único antes de existir autenticação.
- Várias réplicas ainda perdem o histórico até o Redis ser implementado.
- Escalar o Render sem sessão compartilhada pioraria o chat, não melhoraria.
