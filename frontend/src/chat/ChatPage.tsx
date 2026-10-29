import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { deleteSession, loadModels, streamAnswer } from '../api/chatClient.ts'
import { formatSources } from '../api/formatSources.ts'
import { readErrorMessage } from '../api/readErrorMessage.ts'
import type { Citation } from '../api/types.ts'
import { appendStreamError, MESSAGE_MAX_LENGTH, type ChatMessage } from './messages.ts'

const MODELS_FAILURE = 'Não foi possível carregar os modelos.'
const STREAM_FAILURE = 'Falha ao iniciar a resposta.'
const STREAM_INTERRUPTED = 'A resposta não pôde ser concluída.'
const GENERATING = 'Gerando resposta...'
const NEW_CONVERSATION = 'Nova conversa iniciada.'

interface ChatPageProps {
  apiBaseUrl: string
}

/** Chat que consome a API existente, sem chave no navegador. */
export function ChatPage({ apiBaseUrl }: ChatPageProps) {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [canSend, setCanSend] = useState(false)
  const nextId = useRef(1)
  const isSendingRef = useRef(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const listRef = useRef<HTMLElement>(null)

  useEffect(() => {
    let isCurrent = true
    loadModels(apiBaseUrl)
      .then((names) => {
        if (!isCurrent) return
        setModels(names)
        setModel(names[0] ?? '')
        setCanSend(names.length > 0)
        if (names.length === 0) setStatus(MODELS_FAILURE)
      })
      .catch((error: unknown) => {
        if (!isCurrent) return
        setCanSend(false)
        setStatus(readErrorMessage(error, MODELS_FAILURE))
      })
    return () => {
      isCurrent = false
    }
  }, [apiBaseUrl])

  useEffect(() => {
    const list = listRef.current
    if (!list) return
    list.scrollTop = list.scrollHeight
  }, [messages])

  function allocateId(): number {
    const id = nextId.current
    nextId.current += 1
    return id
  }

  async function sendQuestion(question: string) {
    if (!question || !model || isSendingRef.current) return
    isSendingRef.current = true
    setDraft('')
    setIsSending(true)
    setStatus(GENERATING)
    const userId = allocateId()
    const answerId = allocateId()
    setMessages((current) => [
      ...current,
      { id: userId, role: 'user', text: question, isError: false, sources: null },
      { id: answerId, role: 'assistant', text: '', isError: false, sources: null },
    ])
    let citations: Citation[] = []
    try {
      await streamAnswer(
        apiBaseUrl,
        { sessionId, message: question, model },
        {
          onMetadata(next) {
            citations = next
          },
          onToken(content) {
            setMessages((current) =>
              current.map((item) =>
                item.id === answerId ? { ...item, text: item.text + content } : item,
              ),
            )
          },
        },
      )
      const sources = formatSources(citations)
      if (sources) {
        setMessages((current) =>
          current.map((item) => (item.id === answerId ? { ...item, sources } : item)),
        )
      }
      setStatus('')
    } catch (error: unknown) {
      const message = readErrorMessage(error, STREAM_FAILURE)
      const errorId = allocateId()
      setMessages((current) => appendStreamError(current, answerId, message, errorId))
      setStatus(STREAM_INTERRUPTED)
    } finally {
      isSendingRef.current = false
      setIsSending(false)
      inputRef.current?.focus()
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void sendQuestion(draft.trim())
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    void sendQuestion(draft.trim())
  }

  async function beginNewConversation() {
    await deleteSession(apiBaseUrl, sessionId)
    setSessionId(crypto.randomUUID())
    setMessages([])
    setStatus(NEW_CONVERSATION)
    inputRef.current?.focus()
  }

  return (
    <main>
      <header>
        <div>
          <h1>Chatbot de saúde mental</h1>
          <p>Respostas fundamentadas nas apostilas, com indicação das fontes.</p>
        </div>
        <div className="controls">
          <label htmlFor="model">Modelo</label>
          <select
            id="model"
            aria-label="Modelo de linguagem"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          >
            {models.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <button
            id="new-session"
            type="button"
            disabled={isSending}
            onClick={() => void beginNewConversation()}
          >
            Nova conversa
          </button>
        </div>
      </header>

      <section id="messages" ref={listRef} aria-live="polite" aria-label="Conversa">
        {messages.map((item) => (
          <article key={item.id} className={classNameFor(item)}>
            <div>{item.text}</div>
            {item.sources ? <div className="sources">{item.sources}</div> : null}
          </article>
        ))}
      </section>

      <div>
        <form aria-label="Enviar pergunta" onSubmit={handleSubmit}>
          <textarea
            id="message"
            ref={inputRef}
            aria-label="Sua pergunta"
            placeholder="Faça uma pergunta sobre as apostilas..."
            required
            maxLength={MESSAGE_MAX_LENGTH}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={submitOnEnter}
          />
          <button className="primary" id="send" type="submit" disabled={!canSend || isSending}>
            Enviar
          </button>
        </form>
        <div className="status" id="status" role="status">
          {status}
        </div>
      </div>
    </main>
  )
}

function classNameFor(message: ChatMessage): string {
  if (message.role === 'user') return 'message user'
  if (message.isError) return 'message assistant error'
  return 'message assistant'
}
