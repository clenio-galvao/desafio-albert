# ADR 0004 — RAG fundamentado e memória temporária

Status: aceito.

## Contexto

O chatbot deve considerar a conversa, minimizar alucinações e citar a origem
das afirmações. Acrescentar todo o histórico à busca, porém, pode desviar
perguntas novas e independentes. A entrega não exige persistência permanente
das conversas.

## Decisão

Manter sessões no backend com TTL e janela máxima. O histórico é enviado ao
modelo, mas só contextualiza a recuperação quando a pergunta contém sinais de
continuação. Perguntas autônomas são pesquisadas isoladamente.

Aplicar limiar de relevância, recuperar poucos trechos e incluir a página
seguinte para preservar conteúdos consecutivos. O prompt limita a resposta às
fontes, trata documentos como dados não confiáveis, exige título e página e
orienta recusa quando a evidência não basta.

Essas políticas pertencem à aplicação: `SemanticRetriever` coordena embedding,
busca vetorial, expansão e deduplicação; `GroundedPromptBuilder` monta as
mensagens finais. Os adapters se limitam a consultar o índice vetorial e
traduzir mensagens para o protocolo OpenAI-compatible.

## Consequências

- Perguntas independentes não são diluídas pelo assunto anterior.
- Continuações como “e como ela funciona?” preservam o contexto.
- Citações permitem conferir a resposta nas apostilas.
- Trocar Qdrant ou o provedor de LLM não move nem duplica as regras de
  recuperação e grounding.
- Sessões são perdidas em reinícios e não são compartilhadas entre réplicas.
- A heurística de continuação e os parâmetros de recuperação precisam ser
  recalibrados se o comportamento ou a base mudar.
