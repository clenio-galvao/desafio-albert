import { afterEach, describe, expect, it, vi } from 'vitest'
import { deleteSession, joinApiUrl, loadModels, streamAnswer } from './chatClient.ts'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sseResponse(payload: string, status = 200): Response {
  return new Response(payload, {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('joinApiUrl', () => {
  it('appends the path to the public base', () => {
    expect(joinApiUrl('http://localhost:8000', '/v1/models')).toBe(
      'http://localhost:8000/v1/models',
    )
  })

  it('drops a trailing slash from the base', () => {
    expect(joinApiUrl('http://localhost:8000/', '/v1/models')).toBe(
      'http://localhost:8000/v1/models',
    )
  })

  it('keeps a relative path when the base is empty', () => {
    expect(joinApiUrl('', '/v1/models')).toBe('/v1/models')
  })
})

describe('loadModels', () => {
  it('returns the public allowlist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ models: ['model-a', 'model-b'] })),
    )

    await expect(loadModels('http://api.test')).resolves.toEqual(['model-a', 'model-b'])
  })

  it('rejects an HTTP error without reading a secret', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'nope' }, 503)))

    await expect(loadModels('http://api.test')).rejects.toThrow(
      'Não foi possível carregar os modelos.',
    )
  })

  it('rejects a payload that is not the allowlist', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(null)))

    await expect(loadModels('http://api.test')).rejects.toThrow(
      'Não foi possível carregar os modelos.',
    )
  })

  it('rejects a payload whose models field is not a list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ models: 'model-a' })))

    await expect(loadModels('http://api.test')).rejects.toThrow(
      'Não foi possível carregar os modelos.',
    )
  })

  it('rejects a list that contains a non-string model', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ models: ['model-a', 1] })))

    await expect(loadModels('http://api.test')).rejects.toThrow(
      'Não foi possível carregar os modelos.',
    )
  })
})

describe('deleteSession', () => {
  it('calls DELETE with the encoded session id and no credentials', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteSession('http://api.test', 'a/b')

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/v1/sessions/a%2Fb', {
      method: 'DELETE',
      credentials: 'omit',
    })
  })
})

describe('streamAnswer', () => {
  it('posts the chat body and emits citations and tokens', async () => {
    const payload = [
      'event: metadata\ndata: {"citations":[{"source":"a.pdf","title":"Apostila","page":3}]}\n\n',
      'event: token\ndata: {"content":"Olá"}\n\nevent: done\ndata: {}\n\n',
    ].join('')
    const fetchMock = vi.fn(async () => sseResponse(payload))
    vi.stubGlobal('fetch', fetchMock)
    const citations: unknown[] = []
    const tokens: string[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      {
        onMetadata: (items) => citations.push(...items),
        onToken: (content) => tokens.push(content),
      },
    )

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/v1/chat/stream', {
      method: 'POST',
      credentials: 'omit',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: 'session-1',
        message: 'Oi',
        model: 'model-a',
      }),
    })
    expect(citations).toEqual([{ source: 'a.pdf', title: 'Apostila', page: 3 }])
    expect(tokens).toEqual(['Olá'])
  })

  it('joins an event split across reads', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: token\ndata: {"content":"O'))
        controller.enqueue(encoder.encode('lá"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(stream, { status: 200 })),
    )
    const tokens: string[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: () => undefined, onToken: (content) => tokens.push(content) },
    )

    expect(tokens).toEqual(['Olá'])
  })

  it('ignores a done event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: done\ndata: {}\n\n')),
    )
    const tokens: string[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: () => undefined, onToken: (content) => tokens.push(content) },
    )

    expect(tokens).toEqual([])
  })

  it('returns no citations when metadata has no list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: metadata\ndata: {}\n\n')),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([])
  })

  it('skips a citation that is not an object', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(
          'event: metadata\ndata: {"citations":[null,{"source":"a.pdf","title":"A","page":1}]}\n\n',
        ),
      ),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([{ source: 'a.pdf', title: 'A', page: 1 }])
  })

  it('returns no citations when metadata is not an object', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: metadata\ndata: []\n\n')),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([])
  })

  it('skips a citation whose source is not text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(
          'event: metadata\ndata: {"citations":[{"source":1,"title":"A","page":1}]}\n\n',
        ),
      ),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([])
  })

  it('skips a citation with a non-string title', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(
          'event: metadata\ndata: {"citations":[{"source":"a.pdf","title":1,"page":1}]}\n\n',
        ),
      ),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([])
  })

  it('skips a citation whose page is not a number', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(
          'event: metadata\ndata: {"citations":[{"source":"a.pdf","title":"A","page":"1"}]}\n\n',
        ),
      ),
    )
    const citations: unknown[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: (items) => citations.push(...items), onToken: () => undefined },
    )

    expect(citations).toEqual([])
  })

  it('appends nothing when a token payload is not an object', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse('event: token\ndata: []\n\n')))
    const tokens: string[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: () => undefined, onToken: (content) => tokens.push(content) },
    )

    expect(tokens).toEqual([''])
  })

  it('appends nothing when a token has no content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: token\ndata: {}\n\n')),
    )
    const tokens: string[] = []

    await streamAnswer(
      'http://api.test',
      { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
      { onMetadata: () => undefined, onToken: (content) => tokens.push(content) },
    )

    expect(tokens).toEqual([''])
  })

  it('throws the error event message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: error\ndata: {"message":"limite do gateway"}\n\n')),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('limite do gateway')
  })

  it('throws a generic failure when the error event is not an object', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse('event: error\ndata: []\n\n')))

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the error event has no message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: error\ndata: {}\n\n')),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the error message is blank', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: error\ndata: {"message":"  "}\n\n')),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws the HTTP detail when the stream is refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'modelo não autorizado' }, 422)),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('modelo não autorizado')
  })

  it('throws a generic failure when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('nope', { status: 500 })),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the error payload is not an object', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(null, 422)))

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the detail is not text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 1 }, 422)))

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the detail is blank', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: '  ' }, 422)),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when the response has no body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, body: null, json: async () => ({}) }) as Response),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })

  it('throws a generic failure when an SSE block is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse('event: token\ndata: {\n\n')),
    )

    await expect(
      streamAnswer(
        'http://api.test',
        { sessionId: 'session-1', message: 'Oi', model: 'model-a' },
        { onMetadata: () => undefined, onToken: () => undefined },
      ),
    ).rejects.toThrow('Falha ao iniciar a resposta.')
  })
})
