# ADR 0001 — Arquitetura hexagonal e composição explícita

Status: aceito.

## Contexto

A API precisa integrar FastAPI, armazenamento vetorial, sessões e um gateway
de modelos sem acoplar as regras do chatbot a fornecedores específicos. A
solução também precisa ser testável sem rede e explicável durante a avaliação.

## Decisão

Separar o código em domínio, aplicação e adapters. Casos de uso dependem de
portas estruturais; implementações concretas ficam nos adapters. O
`bootstrap.py` é o único composition root e constrói explicitamente o grafo de
dependências.

FastAPI permanece como adapter de entrada. OpenAI-compatible, Qdrant, PDF e
memória TTL são adapters de saída.

O container expõe ao adapter HTTP somente portas de entrada: chat, catálogo de
modelos, encerramento de sessão e readiness. Repositórios e dependências
externas permanecem encapsulados pelos casos de uso. O chat oferece um
preflight de aplicação para validar modelo e tamanho antes de o HTTP iniciar a
resposta SSE.

O router depende do protocolo `ApplicationServices`, definido na aplicação, e
recebe sua implementação pelo estado da aplicação FastAPI. Tanto a API quanto
a ingestão são compostas por fábricas do mesmo `bootstrap.py`; scripts apenas
solicitam o grafo adequado e encerram todos os recursos retornados.

## Consequências

- Regras e testes não dependem de FastAPI, OpenAI ou Qdrant.
- O router não acessa portas de saída nem duplica políticas da aplicação.
- Provedores podem ser substituídos sem alterar os casos de uso.
- A composição fica visível e simples de depurar.
- Há mais interfaces e arquivos do que em uma implementação diretamente
  acoplada ao framework.
