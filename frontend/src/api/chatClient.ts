import { isRecord } from './isRecord.ts'
import { parseSseBlock, pullSseBlocks, type SseEvent } from './parseSse.ts'
import type { ChatRequestBody, ChatStreamHandlers, Citation } from './types.ts'

const STREAM_FAILURE = 'Falha ao iniciar a resposta.'
const MODELS_FAILURE = 'Não foi possível carregar os modelos.'

/** Junta a base pública ao caminho sem duplicar a barra. */
export function joinApiUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/$/, '')}${path}`
}

/** Carrega a allowlist pública, sem revelar o provedor. */
export async function loadModels(baseUrl: string): Promise<string[]> {
  const response = await fetch(joinApiUrl(baseUrl, '/v1/models'))
  if (!response.ok) throw new Error(MODELS_FAILURE)
  const payload: unknown = await response.json()
  if (!isRecord(payload) || !Array.isArray(payload.models) || !payload.models.every(isString)) {
    throw new Error(MODELS_FAILURE)
  }
  return payload.models
}

/** Encerra o histórico temporário da sessão no backend. */
export async function deleteSession(baseUrl: string, sessionId: string): Promise<void> {
  await fetch(joinApiUrl(baseUrl, `/v1/sessions/${encodeURIComponent(sessionId)}`), {
    method: 'DELETE',
    credentials: 'omit',
  })
}

/** Envia a pergunta e entrega tokens assim que cada quadro SSE chega. */
export async function streamAnswer(
  baseUrl: string,
  request: ChatRequestBody,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const response = await fetch(joinApiUrl(baseUrl, '/v1/chat/stream'), {
    method: 'POST',
    credentials: 'omit',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: request.sessionId,
      message: request.message,
      model: request.model,
    }),
  })
  if (!response.ok || response.body === null) {
    throw new Error(await readFailureMessage(response))
  }
  await readSseStream(response.body, (event) => applyChatEvent(event, handlers))
}

async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const pulled = pullSseBlocks(buffer)
    buffer = pulled.rest
    for (const block of pulled.blocks) onEvent(parseSseBlock(block))
    if (done) return
  }
}

function applyChatEvent(event: SseEvent, handlers: ChatStreamHandlers): void {
  if (event.event === 'metadata') {
    handlers.onMetadata(readCitations(event.data))
    return
  }
  if (event.event === 'token') {
    handlers.onToken(readToken(event.data))
    return
  }
  if (event.event === 'error') throw new Error(readStreamError(event.data))
}

function readCitations(data: unknown): Citation[] {
  if (!isRecord(data) || !Array.isArray(data.citations)) return []
  const citations: Citation[] = []
  for (const item of data.citations) {
    if (!isCitation(item)) continue
    citations.push(item)
  }
  return citations
}

function isCitation(value: unknown): value is Citation {
  if (!isRecord(value)) return false
  return (
    typeof value.source === 'string' &&
    typeof value.title === 'string' &&
    typeof value.page === 'number'
  )
}

function readToken(data: unknown): string {
  if (!isRecord(data) || typeof data.content !== 'string') return ''
  return data.content
}

function readStreamError(data: unknown): string {
  if (!isRecord(data) || typeof data.message !== 'string' || !data.message.trim()) {
    return STREAM_FAILURE
  }
  return data.message
}

async function readFailureMessage(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json()
    if (isRecord(payload) && typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail
    }
  } catch {
    return STREAM_FAILURE
  }
  return STREAM_FAILURE
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}
