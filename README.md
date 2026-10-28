# Desafio Albert — Chatbot RAG

API de chatbot em Python com FastAPI que responde, em streaming, somente com
base em quatro apostilas de saúde mental. A solução usa arquitetura hexagonal,
recuperação semântica no Qdrant, modelos OpenAI-compatible intercambiáveis e
memória temporária de conversa.

O código, os testes e o histórico de decisões foram organizados para que a
solução possa ser explicada e evoluída.

## Estado atual

- API, ingestão, RAG conversacional, SSE e demo estão implementados.
- Os modelos disponíveis são `azure/gpt-5-mini` e `azure/gpt-6-luna`.
- Os embeddings usam `cohere/embed-v4.0`.
- A coleção atual possui 257 páginas indexadas.
- A suíte possui mais de 100 testes e cobertura de branches de 100%.
- Aplicação publicada: <https://desafio-albert-chatbot.onrender.com/demo>.

## Base de conhecimento

Foram utilizadas quatro apostilas fornecidas em uma pasta privada do Google
Drive:

- Saúde Mental na Atenção Primária — 63 páginas;
- Ampliando o Conceito de Saúde Mental — 65 páginas;
- O sujeito, a Integralidade e a Saúde Mental — 53 páginas;
- Desenvolvendo os Cuidados de Saúde Mental na APS — 76 páginas.

Os PDFs não são publicados no GitHub. A ingestão extrai o texto de cada página,
normaliza ruídos de layout, divide textos longos em chunks com sobreposição,
gera IDs e hashes determinísticos, cria embeddings e persiste texto, arquivo,
título, página e hash no Qdrant. A reingestão consulta os hashes existentes e não
consome embeddings novamente quando o conteúdo não mudou.

## Arquitetura

```mermaid
flowchart LR
    Client[Demo, Swagger ou Postman] --> API[FastAPI + SSE]
    API --> Chat[GroundedChatService]
    Chat --> Session[SessionRepositoryPort]
    Chat --> Retriever[RetrieverPort]
    Chat --> LLM[LLMPort]
    Session --> Memory[Memória TTL]
    Retriever --> Embedding[EmbeddingPort]
    Retriever --> Index[VectorIndexPort]
    Index --> Qdrant[Qdrant Cloud]
    LLM --> Gateway[API OpenAI-compatible]
    PDFs[PDFs privados] --> Ingest[IngestionService]
    Ingest --> Embedding
    Embedding --> Gateway
    Ingest --> Qdrant
```

- `domain`: entidades e regras sem dependências de frameworks;
- `application`: casos de uso, portas, contextualização, recuperação,
  construção do prompt fundamentado e avaliação;
- `adapters/inbound`: API FastAPI, SSE e página de demonstração;
- `adapters/outbound`: gateway OpenAI-compatible, Qdrant, PDF e sessões;
- `bootstrap.py`: composição explícita das dependências e exposição exclusiva
  de portas de entrada ao adapter HTTP.

As decisões e alternativas estão registradas em [docs/adr](docs/adr/README.md).

## Fluxo do RAG

1. A pergunta é validada e associada a uma sessão temporária.
2. Perguntas independentes são pesquisadas sem contaminar a consulta com o
   histórico; referências como “isso” ou “ela” usam os turnos recentes.
3. O recuperador da aplicação solicita a `cohere/embed-v4.0` o vetor da consulta.
4. O adapter Qdrant busca os três vetores mais próximos com score mínimo de
   `0.35`, sem conter regras de recuperação.
5. Uma página seguinte é incluída para preservar listas e explicações
   interrompidas por quebra de página.
6. A aplicação monta as mensagens com histórico limitado, pergunta, fontes
   delimitadas como conteúdo não confiável e títulos persistidos na ingestão.
7. A resposta é transmitida por SSE e deve citar título e página.

O prompt proíbe conhecimento externo, diagnósticos e instruções encontradas
nos documentos. Na ausência de evidência suficiente, o caso de uso recusa a
resposta antes de chamar o modelo quando nenhum trecho supera o limiar.

## Requisitos e instalação

- Python 3.12 ou superior;
- conta/coleção no Qdrant;
- endpoint e chave OpenAI-compatible fornecidos para o desafio.

```bash
python -m venv .venv
```

No Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

No Linux ou macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Preencha no `.env` pelo menos `OPENAI_BASE_URL`, `OPENAI_API_KEY`,
`QDRANT_URL` e `QDRANT_API_KEY`. As demais opções possuem exemplos seguros em
[.env.example](.env.example).

## Preparação da base

O download e a ingestão são comandos explícitos; iniciar a API não reindexa
documentos nem consome embeddings:

```bash
python scripts/download_documents.py
python scripts/ingest.py
```

O primeiro comando salva os PDFs em `data/documents`, ignorado pelo Git. O
segundo imprime `documents`, `chunks`, `embedded_chunks` e `skipped_chunks`.
Revise o `.env` antes da ingestão, pois novos chunks consomem a cota do gateway.
Coleções criadas antes da inclusão do metadado `title` podem ser atualizadas,
sem recalcular embeddings, com `python scripts/migrate_qdrant_titles.py`.

## Execução e teste manual

```bash
uvicorn chatbot.main:app --reload
```

- Demo: `http://localhost:8000/demo`;
- Swagger: `http://localhost:8000/docs`;
- liveness: `http://localhost:8000/health/live`;
- readiness do Qdrant: `http://localhost:8000/health/ready`;
- coleção Postman: `docs/postman/chatbot-rag.postman_collection.json`.

Exemplo de streaming:

```bash
curl -N -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"O que é escuta terapêutica?","model":"azure/gpt-5-mini"}'
```

O endpoint envia `metadata`, um ou mais eventos `token`, `done` e, em falhas
iniciadas após os cabeçalhos HTTP, `error`. O roteiro completo está em
[docs/DEMO.md](docs/DEMO.md).

## API

- `POST /v1/chat/stream`: recebe `session_id`, `message` e `model`;
- `GET /v1/models`: retorna a allowlist de modelos;
- `DELETE /v1/sessions/{session_id}`: apaga o histórico temporário;
- `GET /health/live`: confirma que o processo está ativo;
- `GET /health/ready`: confirma acesso à coleção no Qdrant;
- `GET /demo`: disponibiliza o cliente web mínimo.

`session_id` aceita letras, números, ponto, hífen, sublinhado e dois-pontos,
com até 128 caracteres. Campos extras e modelos fora da allowlist retornam
HTTP 422. Modelo e limite configurável da mensagem são validados pela aplicação
antes de o transporte iniciar a resposta SSE.

## Streaming SSE

A resposta chega por Server-Sent Events, não por WebSocket. Depois do
`POST /v1/chat/stream`, o fluxo é só servidor → cliente: `metadata`,
tokens e `done` (ou `error`). Cancelar é fechar o HTTP; a próxima
pergunta é outro POST.

SSE foi escolhido porque continua sendo HTTP: a demo usa `fetch`, o
Swagger e o Postman funcionam, `curl -N` observa o stream e a chave
permanece no backend. WebSocket exigiria handshake extra e só se
justificaria se o cliente precisasse enviar mensagens durante a
geração.

SSE usa TCP. Pacote IP perdido é retransmitido e reordenado pela
própria conexão; o browser não recebe o token 3 sem o 2. O que parece
perda de pacote na prática é queda de conexão, timeout de proxy ou
bufferização.

Hoje a API desliga o cache (`Cache-Control: no-cache`,
`X-Accel-Buffering: no`) e interrompe a geração se o cliente
desconectar. A demo só conclui a resposta ao receber `done`. Sem
`done`, o histórico não grava a resposta parcial e a pergunta pode
ser reenviada. Não usamos `EventSource` nativo porque ele só faz GET.

Se um dia for necessário não perder tokens já gerados, a ordem seria:
comentários de keepalive no SSE para evitar idle timeout; retry da
pergunta; depois buffer com `id` de evento e um `GET` de retomada
(`Last-Event-ID`). WebSocket também é TCP: não elimina perda de
pacotes e continuaria precisando de sequência e buffer no servidor.

A decisão está em [ADR 0003](docs/adr/0003-openai-compatible-sse.md).

## Qualidade e avaliação

```bash
pytest
ruff check .
mypy
```

A CI executa essas três verificações em Python 3.12. Os testes são offline,
usam fakes/mocks e cobrem adapters, ingestão idempotente, Qdrant, PDFs
inválidos, memória, múltiplos turnos, erros e desconexões de streaming.

O dataset em `evaluation/rag_cases.json` contém perguntas respondíveis,
recusa fora do escopo e conversa com múltiplos turnos. A suíte offline percorre
o `GroundedChatService` e mede recuperação, citação, conceitos essenciais e
recusa sem fazer chamadas pagas.

A avaliação real exige a API em execução e confirmação explícita:

```bash
python scripts/evaluate_rag.py --confirm-live
```

Também são aceitos `--base-url`, `--model` e `--dataset`. Esse comando consome
cota e não é executado pela CI.

## Deploy no Render

O repositório contém `Dockerfile` e `render.yaml`. A imagem instala somente a
aplicação e executa como usuário sem privilégios; PDFs, testes, `.env` e dados
locais não entram no build.

- Demo pública: <https://desafio-albert-chatbot.onrender.com/demo>;
- Swagger público: <https://desafio-albert-chatbot.onrender.com/docs>;
- Health check: <https://desafio-albert-chatbot.onrender.com/health/ready>.

1. Envie a branch principal ao GitHub.
2. No Render, crie um Blueprint a partir do repositório.
3. Preencha os quatro valores marcados com `sync: false`:
   `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `QDRANT_URL` e `QDRANT_API_KEY`.
4. Confirme que `QDRANT_COLLECTION` aponta para a coleção já ingerida.
5. Aguarde `/health/ready` ficar saudável e valide `/demo`.

A aplicação respeita a variável `PORT` da plataforma. A ingestão não ocorre
durante o deploy; a coleção deve estar pronta no Qdrant. Em plano gratuito, o
primeiro acesso depois de um período ocioso pode sofrer cold start de
aproximadamente 50 segundos ou mais.

## Mídias presentes nas apostilas

Na implementação atual, a ingestão processa somente o texto extraível dos
PDFs. Textos que transcrevem um áudio dentro da própria página são indexados,
mas arquivos de áudio incorporados, destinos de links e conteúdos de vídeos do
YouTube não são acessados nem transcritos.

Uma evolução futura poderá adicionar suporte a essas mídias durante a ingestão,
nunca durante uma pergunta do usuário:

1. Extrair anotações de links e arquivos incorporados, preservando PDF e página
   de origem.
2. Obter legendas ou transcrições já disponíveis nos vídeos.
3. Usar um serviço de transcrição, como Whisper, somente quando não houver
   texto disponível e após avaliar custo, licença e requisitos de execução.
4. Dividir transcrições por intervalos de tempo, gerar embeddings e armazená-las
   no Qdrant com URL, página, título e timestamp.
5. Exibir referências no formato
   `[Título da apostila, p. 29, áudio 00:37]`.

Para manter a arquitetura hexagonal, essa evolução deverá introduzir portas
como `MediaExtractorPort` e `TranscriptionPort`, adaptadores específicos para
PDF, YouTube e transcrição, além de um caso de uso de ingestão multimídia.

Downloads deverão aceitar apenas domínios permitidos, com limites de duração,
tamanho e tempo de resposta para mitigar SSRF e consumo abusivo. Os testes
automatizados usarão mídias simuladas e não dependerão de rede no CI. O
processamento será prévio à publicação, mantendo a API de consulta leve e
compatível com hospedagem gratuita.

## Segurança

Copie `.env.example` para `.env` e preencha as credenciais apenas localmente.
Nunca faça commit de chaves, apostilas em PDF ou índices gerados.

- Credenciais são lidas somente no backend e não chegam à demo.
- Modelos são limitados por allowlist.
- Schemas rejeitam campos extras e limitam tamanho e formato das entradas.
- Logs não incluem chaves nem o conteúdo integral das mensagens.
- Documentos são delimitados como dados não confiáveis contra prompt injection.
- CORS fica desabilitado por padrão e aceita apenas origens explícitas.
- Sessões expiram por TTL e possuem limite de mensagens.

Esta API oferece conteúdo educacional baseado nas apostilas; não substitui
avaliação profissional e não deve realizar diagnóstico médico.

## Custos e desempenho

- A ingestão é offline e idempotente para evitar embeddings repetidos.
- A consulta realiza um embedding e uma geração por pergunta respondível.
- Perguntas sem evidência não chamam o modelo de geração.
- A memória é local ao processo e pode ser perdida em reinícios ou cold starts.
- O Qdrant externo evita reconstruir o índice no ambiente gratuito.
- A avaliação real nunca roda automaticamente.

## Escalabilidade

Cada usuário recebe a resposta no próprio SSE. O Uvicorn multiplexa as
conexões no mesmo processo (`WEB_CONCURRENCY=1` no Render Free). Não há fila
única: o que limita o conjunto é a instância, o teto `MAX_CONCURRENT_STREAMS`
(HTTP 429) e a cota do gateway.

Teste de carga **local**, sem gastar cota:

```bash
python scripts/load_test.py --users 25 --requests 100
```

Resultado em 2026-10-28: 100 streams concluídos, 0% de erro, primeiro token
p95 de 90 ms. A API aguenta o cenário de 25 usuários simultâneos; o ponto
fraco em produção é o LLM/embedding, não o FastAPI.

Perfil publicado, no máximo 5 requisições reais:

```bash
python scripts/load_test.py --target https://desafio-albert-chatbot.onrender.com --users 1 --requests 3
```

Se a carga real for insatisfatória, a ordem é: 429 e timeout (já ativos),
depois Redis no `SessionRepositoryPort`, e só então mais workers ou plano do
Render. Subir réplicas antes do Redis quebra o histórico da conversa. Detalhes
em [ADR 0005](docs/adr/0005-escalabilidade-carga.md).

## Decisões e limitações

- Sessões em memória simplificam a entrega; múltiplas réplicas exigiriam Redis
  ou outro repositório compartilhado.
- A recuperação é vetorial densa, sem reranker ou busca lexical híbrida.
- O limiar `0.35`, `top_k=3` e uma página seguinte foram calibrados com casos
  reais das apostilas e devem ser reavaliados se a base mudar.
- Uma página curta pode corresponder a um chunk; páginas longas são divididas
  conforme `CHUNK_SIZE_TOKENS` e `CHUNK_OVERLAP_TOKENS`.
- O provedor é OpenAI-compatible, mas disponibilidade, latência e limites dos
  modelos continuam sendo responsabilidades externas.
- Áudios e vídeos ainda não são ingeridos, conforme a seção anterior.
- O streaming é SSE unidirecional; WebSocket ficaria para tráfego
  bidirecional. Pacotes perdidos na rede são recuperados pelo TCP;
  queda de conexão se trata com retry ou, se necessário, retomada por
  `id` de evento, como na seção de streaming.

## Convenções de código

O estilo do repositório fica nas regras do Cursor, lidas em toda sessão
de implementação:

- [.cursor/rules/clean-code-python.mdc](.cursor/rules/clean-code-python.mdc)
  — imports só no topo do módulo, uma responsabilidade por função,
  constantes nomeadas, arquitetura hexagonal e docstring de uma linha
  em português;
- [.cursor/rules/nomenclatura.mdc](.cursor/rules/nomenclatura.mdc)
  — verbos na ação (`search`, `require_container`), `build_` em
  fábricas, `as_` em conversão, `is_`/`has_` em booleanos;
- [.cursor/rules/pytest-um-comportamento.mdc](.cursor/rules/pytest-um-comportamento.mdc)
  — um comportamento por teste; `parametrize` quando os casos
  compartilham o mesmo acto.

O Ruff reforça import fora do topo (`PLC0415`). Casos de uso de disparo
único expõem `execute`; o chat usa `validate` e `stream` porque o canal
permanece aberto.

## Uso de IA no desenvolvimento

IA generativa foi utilizada como ferramenta de apoio para planejamento,
implementação, criação de testes, revisão de cenários, diagnóstico da
recuperação e redação inicial da documentação. As decisões foram validadas com
execução local, inspeção dos textos realmente armazenados no Qdrant, testes
automatizados, Ruff e mypy.

Não foram delegados à IA segredos, publicação de PDFs ou decisões clínicas. O
desenvolvedor permanece responsável por revisar o código, explicar as escolhas,
validar resultados e controlar chamadas que consomem orçamento.

## Estrutura do projeto

```text
src/chatbot/          aplicação, domínio e adapters
scripts/              download, ingestão, avaliação real e carga
evaluation/           dataset versionado de avaliação
tests/                testes unitários, integração e avaliação offline
docs/adr/             decisões arquiteturais
docs/postman/         coleção para teste manual
.cursor/rules/        convenções persistentes de código e testes
ROADMAP.md            tarefas e histórico de execução
```

## Documentação complementar

- [Roadmap e checklist por commit](ROADMAP.md);
- [ADRs](docs/adr/README.md);
- [Roteiro de demonstração e troubleshooting](docs/DEMO.md);
- [Clean code](.cursor/rules/clean-code-python.mdc),
  [nomenclatura](.cursor/rules/nomenclatura.mdc) e
  [testes](.cursor/rules/pytest-um-comportamento.mdc).
