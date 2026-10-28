# Roteiro de demonstração e troubleshooting

## Preparação

1. Confirme que `.env` contém o gateway, os modelos e o Qdrant.
2. Execute `python scripts/ingest.py` e verifique que os chunks existentes
   aparecem como `skipped_chunks`.
3. Inicie com `uvicorn chatbot.main:app --reload`.
4. Abra `http://localhost:8000/health/ready`; o esperado é
   `{"status":"ready"}`.
5. Abra `http://localhost:8000/demo`.

## Demonstração sugerida

### 1. Recuperação e citação

Pergunte:

> O que é escuta terapêutica?

Verifique que a resposta usa a apostila **O sujeito, a Integralidade e a Saúde
Mental**, página 29, e que a referência aparece uma vez ao final do parágrafo
ou lista.

### 2. Conteúdo entre páginas

Pergunte:

> Quais ferramentas podem ser implementadas na prática clínica?

Verifique que a resposta reúne os sete itens das páginas 9 e 10 de
**Desenvolvendo os Cuidados de Saúde Mental na APS**.

### 3. Histórico

Após uma pergunta respondida, faça uma continuação:

> E como ela melhora a comunicação?

O backend mantém o histórico da sessão. Uma pergunta independente posterior
não deve ser desviada pelo assunto anterior.

### 4. Recusa segura

Pergunte:

> Qual é a capital do Canadá?

O chatbot deve informar que não encontrou evidência suficiente nas apostilas,
sem completar a resposta com conhecimento externo.

### 5. Modelos e streaming

Troque entre `azure/gpt-5-mini` e `azure/gpt-6-luna`. Os dois usam o mesmo
endpoint, e a resposta deve aparecer incrementalmente. Clique em **Nova
conversa** para apagar a sessão atual.

## Outros clientes

- Swagger: `http://localhost:8000/docs`;
- Postman: importe `docs/postman/chatbot-rag.postman_collection.json`;
- terminal no Windows:

```powershell
curl.exe -N -X POST http://localhost:8000/v1/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo","message":"O que é escuta terapêutica?","model":"azure/gpt-5-mini"}'
```

## Troubleshooting

### Alterei `.env`, mas nada mudou

O reload do Uvicorn pode não observar mudanças em `.env`. Pare e inicie o
processo novamente.

### `/health/ready` retorna 503

Confirme `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, conectividade e
se a coleção foi criada pela ingestão.

### A API inicia, mas não há documentos

Execute primeiro `python scripts/download_documents.py` e depois
`python scripts/ingest.py`. O diretório padrão é `data/documents`.

### A resposta não encontra uma página conhecida

1. Inicie uma nova conversa para eliminar contexto anterior.
2. Confira se a página está no Qdrant e se seu texto foi extraído.
3. Compare `RETRIEVAL_SCORE_THRESHOLD` e `RETRIEVAL_TOP_K`.
4. Acrescente o caso ao dataset antes de recalibrar parâmetros.

Não reduza o limiar apenas para resolver um exemplo: isso pode aumentar fontes
irrelevantes e alucinações.

### A resposta ainda mostra comportamento antigo

Reinicie a API e atualize a página da demo. Mudanças em prompt, títulos ou
frontend não exigem reingestão. Mudanças nos PDFs, chunking ou embeddings podem
exigir nova ingestão e, dependendo da compatibilidade, outra coleção.

### O streaming parece chegar inteiro

Use `curl.exe -N` ou a demo. Proxies podem aplicar buffering; a API envia
`Cache-Control: no-cache` e `X-Accel-Buffering: no`.

### Erro 422

Confira o modelo em `GET /v1/models`, o formato de `session_id`, o tamanho da
mensagem e se o JSON não contém campos extras.

### A avaliação real não inicia

O script exige `--confirm-live` para evitar consumo acidental:

```bash
python scripts/evaluate_rag.py --confirm-live
```

Mantenha a API ativa durante a execução. A CI nunca executa essa avaliação.
