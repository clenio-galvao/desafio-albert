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

## Teste ao vivo

- Demo: `http://localhost:8000/demo`
- Swagger: `http://localhost:8000/docs`
- Coleção Postman: `docs/postman/chatbot-rag.postman_collection.json`

O streaming também pode ser observado diretamente no terminal:

```bash
curl -N -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"Como cuidar da saúde mental?","model":"azure/gpt-5-mini"}'
```

O endpoint envia eventos SSE `metadata`, `token`, `done` e, em caso de falha
após o início do stream, `error`.

## Avaliação do RAG

A suíte padrão é totalmente offline e usa fakes/mocks, sem consumir a cota dos
modelos:

```bash
pytest
ruff check .
mypy
```

O dataset versionado em `evaluation/rag_cases.json` contém perguntas
respondíveis, recusa fora do escopo e conversa com múltiplos turnos. O
avaliador mede recuperação da página esperada, presença da citação,
cobertura dos conceitos essenciais e recusa segura.

A avaliação real é separada dos testes automatizados e só executa após uma
confirmação explícita. Ela requer a API local em funcionamento e realiza
chamadas que podem consumir a cota compartilhada:

```bash
python scripts/evaluate_rag.py --confirm-live
```

Também é possível informar `--base-url`, `--model` e `--dataset`. O comando
retorna código diferente de zero se algum caso não atingir seus critérios.

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
