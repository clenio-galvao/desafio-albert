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
- SSE corre sobre TCP: pacote IP perdido é retransmitido e reordenado. O que
  aparece como perda no frontend é queda de conexão, timeout de proxy ou
  bufferização, não um token isolado faltando.
- A API desliga cache e buffering (`Cache-Control: no-cache`,
  `X-Accel-Buffering: no`) e encerra a geração se o cliente desconectar.
  Sem `done`, a sessão não grava a resposta parcial; o cliente pode
  reenviar a pergunta.
- `EventSource` nativo não se aplica ao `POST` atual. Retomada de tokens
  já gerados exigiria `id` de evento, buffer no servidor e um `GET` com
  `Last-Event-ID`. WebSocket não elimina essa necessidade: também é TCP.
- Particularidades não padronizadas de um provedor podem exigir extensão do
  adapter.
