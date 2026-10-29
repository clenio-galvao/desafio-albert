# ADR 0006 — Observabilidade com OpenTelemetry e Grafana Cloud

Status: aceito.

## Contexto

A API já expõe liveness, readiness do Qdrant e poucos logs de erro. Isso não
mostra em qual etapa uma pergunta ficou lenta, se o RAG passou a recusar mais,
nem se o gate de streams está saturado. O plano gratuito do Render não comporta
Grafana, Loki e um collector no mesmo processo do Uvicorn.

As apostilas são de saúde mental. Mensagem, prompt e chunks não podem ir para
logs, traces ou métricas.

## Decisão

Instrumentar com OpenTelemetry e exportar traces e métricas por OTLP direto ao
Grafana Cloud, sem sidecar. Spans são manuais: `chat.stream`, `retrieval`,
`embed`, `qdrant` e `llm`. Não há autoinstrumentação de FastAPI, HTTP ou do SDK
do modelo.

O domínio e os casos de uso dependem de uma porta de observabilidade. O SDK
fica no adapter e é composto só no `bootstrap.py`. Sem
`OTEL_EXPORTER_OTLP_ENDPOINT`, a API sobe e continua emitindo logs JSON no
stdout. Falha ao montar o exportador também cai nesse modo.

Logs JSON incluem `request_id`, `trace_id` e `span_id` quando existem. O
`session_id` sai apenas como fingerprint SHA-256 truncado. A amostragem padrão
é 100% em desenvolvimento e 20% no Blueprint do Render.

## Alternativas descartadas

- Só logs no painel do Render: não separam retrieval de geração.
- Prometheus scrape em `/metrics`: o plano Free não raspa a instância.
- Datadog ou New Relic: prendem a API a um fornecedor e custam mais cedo.
- Grafana self-hosted ou Alloy no Render Free: disputam memória com o chat e
  pioram o cold start.
- Autoinstrumentação: captura corpos HTTP, prompts e respostas.

## Consequências

- Um trace no Grafana mostra se a demora foi embedding, Qdrant ou o modelo.
- Métricas cobrem streams ativos, HTTP 429, desfecho, tempo até o primeiro
  token e latência de Qdrant e do gateway.
- A CI não fala com o Grafana; os testes usam fakes e exportadores em memória.
- Logs da conversa continuam no stdout do Render, correlacionáveis pelo
  `trace_id` copiado para o Grafana.
- Sem o endpoint configurado, não há traces remotos. O chat não depende deles.
