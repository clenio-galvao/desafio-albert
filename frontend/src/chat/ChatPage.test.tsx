import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPage } from './ChatPage.tsx'

interface Call {
  url: string
  init?: RequestInit
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sseResponse(payload: string): Response {
  return new Response(payload, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

const SESSION_A = '11111111-1111-4111-8111-111111111111'
const SESSION_B = '22222222-2222-4222-8222-222222222222'
const SESSION_C = '33333333-3333-4333-8333-333333333333'

const answer = [
  'event: metadata\n',
  'data: {"citations":[{"source":"a.pdf","title":"Apostila","page":3}]}\n\n',
  'event: token\ndata: {"content":"Olá"}\n\n',
  'event: done\ndata: {}\n\n',
].join('')

function installApi(overrides?: {
  models?: () => Response | Promise<Response>
  stream?: () => Response | Promise<Response>
}): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, init })
      if (url.endsWith('/v1/models')) {
        return overrides?.models?.() ?? jsonResponse({ models: ['model-a', 'model-b'] })
      }
      if (url.includes('/v1/sessions/')) return new Response(null, { status: 204 })
      return overrides?.stream?.() ?? sseResponse(answer)
    }),
  )
  return calls
}

async function renderReadyChat(): Promise<Call[]> {
  const calls = installApi()
  render(<ChatPage apiBaseUrl="http://api.test" />)
  expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
  return calls
}

beforeEach(() => {
  vi.spyOn(crypto, 'randomUUID')
    .mockReturnValueOnce(SESSION_A)
    .mockReturnValueOnce(SESSION_B)
    .mockReturnValue(SESSION_C)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ChatPage', () => {
  it('loads the allowlist and enables sending', async () => {
    await renderReadyChat()

    expect(screen.getByRole('button', { name: 'Enviar' })).toBeEnabled()
  })

  it('keeps sending disabled when the allowlist is empty', async () => {
    installApi({ models: () => jsonResponse({ models: [] }) })
    render(<ChatPage apiBaseUrl="http://api.test" />)

    expect(await screen.findByText('Não foi possível carregar os modelos.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
  })

  it('keeps sending disabled when the allowlist fails', async () => {
    installApi({ models: () => jsonResponse({}, 503) })
    render(<ChatPage apiBaseUrl="http://api.test" />)

    expect(await screen.findByText('Não foi possível carregar os modelos.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
  })

  it('shows the network error and keeps sending disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('falha de rede')
      }),
    )
    render(<ChatPage apiBaseUrl="http://api.test" />)

    expect(await screen.findByText('falha de rede')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
  })

  it('ignores models that arrive after the page closes', async () => {
    let resolveModels: (response: Response) => void = () => undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveModels = resolve
          }),
      ),
    )
    const { unmount } = render(<ChatPage apiBaseUrl="http://api.test" />)
    unmount()

    await act(async () => {
      resolveModels(jsonResponse({ models: ['model-a'] }))
    })

    expect(screen.queryByRole('option', { name: 'model-a' })).not.toBeInTheDocument()
  })

  it('ignores a model failure that arrives after the page closes', async () => {
    let rejectModels: (error: Error) => void = () => undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((_resolve, reject) => {
            rejectModels = reject
          }),
      ),
    )
    const { unmount } = render(<ChatPage apiBaseUrl="http://api.test" />)
    unmount()

    await act(async () => {
      rejectModels(new Error('tarde'))
    })

    expect(screen.queryByText('tarde')).not.toBeInTheDocument()
  })

  it('streams the answer and the sources', async () => {
    const calls = await renderReadyChat()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByText('Olá')).toBeInTheDocument()
    expect(screen.getByText('Oi')).toBeInTheDocument()
    expect(screen.getByText('Fontes consultadas: Apostila, p. 3')).toBeInTheDocument()
    expect(screen.getByRole('status').textContent).toBe('')
    expect(screen.getByLabelText('Sua pergunta')).toHaveValue('')
    expect(screen.getByLabelText('Sua pergunta')).toHaveFocus()
    const streamCall = calls.find((call) => call.url.endsWith('/v1/chat/stream'))
    expect(JSON.parse(String(streamCall?.init?.body))).toEqual({
      session_id: SESSION_A,
      message: 'Oi',
      model: 'model-a',
    })
  })

  it('shows the answer without a source line when no citation arrives', async () => {
    installApi({
      stream: () =>
        sseResponse('event: metadata\ndata: {"citations":[]}\n\nevent: token\ndata: {"content":"Sem fonte"}\n\n'),
    })
    render(<ChatPage apiBaseUrl="http://api.test" />)
    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByText('Sem fonte')).toBeInTheDocument()
    expect(screen.queryByText(/Fontes consultadas/)).not.toBeInTheDocument()
  })

  it('renders token text without interpreting markup', async () => {
    installApi({
      stream: () =>
        sseResponse('event: token\ndata: {"content":"<script>alert(1)</script>"}\n\n'),
    })
    render(<ChatPage apiBaseUrl="http://api.test" />)
    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    const token = await screen.findByText('<script>alert(1)</script>')
    expect(token.closest('article')?.querySelector('script')).toBeNull()
  })

  it('shows the HTTP error in the answer bubble', async () => {
    installApi({
      stream: () => jsonResponse({ detail: 'modelo não autorizado' }, 422),
    })
    render(<ChatPage apiBaseUrl="http://api.test" />)
    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    const failure = await screen.findByText('modelo não autorizado')
    expect(failure.closest('article')).toHaveClass('error')
    expect(screen.getByRole('status').textContent).toBe('A resposta não pôde ser concluída.')
    expect(screen.getByLabelText('Sua pergunta')).toHaveFocus()
  })

  it('keeps the partial answer when the stream fails afterwards', async () => {
    installApi({
      stream: () =>
        sseResponse(
          'event: token\ndata: {"content":"Olá"}\n\nevent: error\ndata: {"message":"limite do gateway"}\n\n',
        ),
    })
    render(<ChatPage apiBaseUrl="http://api.test" />)
    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByText('limite do gateway')).toBeInTheDocument()
    expect(screen.getByText('Olá')).toBeInTheDocument()
  })

  it('sends the model selected by the user', async () => {
    const calls = await renderReadyChat()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Modelo de linguagem'), 'model-b')
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByText('Olá')

    const streamCall = calls.find((call) => call.url.endsWith('/v1/chat/stream'))
    expect(JSON.parse(String(streamCall?.init?.body)).model).toBe('model-b')
  })

  it('does not send a blank question', async () => {
    const calls = await renderReadyChat()

    fireEvent.submit(screen.getByRole('form', { name: 'Enviar pergunta' }))

    expect(calls.some((call) => call.url.endsWith('/v1/chat/stream'))).toBe(false)
  })

  it('does not send before a model is available', async () => {
    let resolveModels: (response: Response) => void = () => undefined
    const calls: Call[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push({ url: String(input), init })
        return new Promise<Response>((resolve) => {
          resolveModels = resolve
        })
      }),
    )
    render(<ChatPage apiBaseUrl="http://api.test" />)
    fireEvent.change(screen.getByLabelText('Sua pergunta'), { target: { value: 'Oi' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Enviar pergunta' }))

    expect(calls.some((call) => call.url.endsWith('/v1/chat/stream'))).toBe(false)
    await act(async () => {
      resolveModels(jsonResponse({ models: ['model-a'] }))
    })
  })

  it('ignores a second submit while the answer is still streaming', async () => {
    let release: (response: Response) => void = () => undefined
    const calls = installApi({
      stream: () =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    })
    render(<ChatPage apiBaseUrl="http://api.test" />)
    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Sua pergunta'), { target: { value: 'Oi' } })
    const form = screen.getByRole('form', { name: 'Enviar pergunta' })
    fireEvent.submit(form)
    fireEvent.submit(form)

    expect(calls.filter((call) => call.url.endsWith('/v1/chat/stream'))).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
    await act(async () => {
      release(sseResponse(answer))
    })
    expect(await screen.findByText('Olá')).toBeInTheDocument()
  })

  it('submits the question when Enter is pressed', async () => {
    await renderReadyChat()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi{Enter}')

    expect(await screen.findByText('Olá')).toBeInTheDocument()
  })

  it('inserts a newline when Shift and Enter are pressed', async () => {
    const calls = await renderReadyChat()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi{Shift>}{Enter}{/Shift}')

    expect(screen.getByLabelText('Sua pergunta')).toHaveValue('Oi\n')
    expect(calls.some((call) => call.url.endsWith('/v1/chat/stream'))).toBe(false)
  })

  it('limits the question to 4000 characters', async () => {
    await renderReadyChat()

    expect(screen.getByLabelText('Sua pergunta')).toHaveAttribute('maxLength', '4000')
  })

  it('starts a new conversation and the next question uses another session', async () => {
    const calls = await renderReadyChat()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Sua pergunta'), 'Oi{Enter}')
    expect(await screen.findByText('Olá')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Nova conversa' }))

    expect(screen.queryByText('Olá')).not.toBeInTheDocument()
    expect(screen.getByRole('status').textContent).toBe('Nova conversa iniciada.')
    expect(
      calls.some(
        (call) =>
          call.url === `http://api.test/v1/sessions/${SESSION_A}` &&
          call.init?.method === 'DELETE',
      ),
    ).toBe(true)
    expect(screen.getByLabelText('Sua pergunta')).toHaveFocus()

    await user.type(screen.getByLabelText('Sua pergunta'), 'Outra{Enter}')
    await screen.findByText('Olá')
    const bodies = calls
      .filter((call) => call.url.endsWith('/v1/chat/stream'))
      .map((call) => JSON.parse(String(call.init?.body)) as { session_id: string })
    expect(bodies.map((body) => body.session_id)).toEqual([SESSION_A, SESSION_B])
  })
})
