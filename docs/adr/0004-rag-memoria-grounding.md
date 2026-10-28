# ADR 0004 — RAG fundamentado e memória temporária

Status: aceito.

## Contexto

O chatbot deve considerar a conversa, minimizar alucinações e citar a origem
das afirmações. Acrescentar todo o histórico à busca, porém, pode desviar
perguntas novas e independentes. A entrega não exige persistência permanente
das conversas.

## Decisão

Manter sessões no backend com TTL, janela máxima e um teto de sessões
simultâneas (`SESSION_MAX_COUNT`). Sessões expiradas são removidas a cada
acesso ao repositório; acima do teto, a sessão salva há mais tempo é
descartada. O histórico é enviado ao
modelo, mas só contextualiza a recuperação quando a pergunta contém sinais de
continuação. Perguntas autônomas são pesquisadas isoladamente.

Aplicar limiar de relevância, recuperar poucos trechos e incluir o primeiro
trecho da página seguinte para preservar conteúdos consecutivos. Cada chunk
guarda sua posição na página (`position`), porque o Qdrant devolve os pontos
em ordem de ID, não de leitura. O prompt limita a resposta às
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
- A memória das sessões é limitada; sob volume excessivo, conversas antigas
  são encerradas antes de expirarem.
- A heurística de continuação e os parâmetros de recuperação precisam ser
  recalibrados se o comportamento ou a base mudar.
