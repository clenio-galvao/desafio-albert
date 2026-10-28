# ADR 0003 — Gateway OpenAI-compatible e streaming SSE

Status: aceito.

## Contexto

Dois modelos de linguagem devem ser selecionáveis sem duplicar integrações. A
resposta precisa chegar progressivamente ao cliente e a chave deve permanecer
exclusivamente no backend.

## Decisão

Usar o SDK da OpenAI com `base_url` e chave configurados por ambiente. Uma
allowlist controla os nomes aceitos, enquanto um único adapter atende todos os
modelos compatíveis.

Expor a geração por Server-Sent Events. O servidor envia metadados de fontes,
tokens incrementais e conclusão. Erros posteriores ao início do stream também
são eventos SSE seguros.

## Consequências

- Trocar de modelo não exige outro adapter.
- A chave nunca é enviada ao navegador.
- SSE funciona com HTTP comum e é fácil de observar com `curl -N`.
- O fluxo é unidirecional; necessidades bidirecionais futuras poderiam exigir
  WebSocket.
- Particularidades não padronizadas de um provedor podem exigir extensão do
  adapter.
