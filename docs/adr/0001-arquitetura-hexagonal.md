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

## Consequências

- Regras e testes não dependem de FastAPI, OpenAI ou Qdrant.
- Provedores podem ser substituídos sem alterar os casos de uso.
- A composição fica visível e simples de depurar.
- Há mais interfaces e arquivos do que em uma implementação diretamente
  acoplada ao framework.
