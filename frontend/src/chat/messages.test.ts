import { describe, expect, it } from 'vitest'
import { appendStreamError, type ChatMessage } from './messages.ts'

const user: ChatMessage = {
  id: 1,
  role: 'user',
  text: 'Oi',
  isError: false,
  sources: null,
}

describe('appendStreamError', () => {
  it('returns the same messages when the answer is missing', () => {
    const result = appendStreamError([user], 9, 'falhou', 3)

    expect(result).toEqual([user])
  })

  it('replaces an empty answer with the error', () => {
    const answer: ChatMessage = {
      id: 2,
      role: 'assistant',
      text: '',
      isError: false,
      sources: null,
    }

    expect(appendStreamError([user, answer], 2, 'falhou', 3)[1]).toEqual({
      id: 2,
      role: 'assistant',
      text: 'falhou',
      isError: true,
      sources: null,
    })
  })

  it('keeps the partial answer and adds the error after it', () => {
    const answer: ChatMessage = {
      id: 2,
      role: 'assistant',
      text: 'Olá',
      isError: false,
      sources: null,
    }

    const result = appendStreamError([user, answer], 2, 'falhou', 3)

    expect(result).toHaveLength(3)
    expect(result[2]).toEqual({
      id: 3,
      role: 'assistant',
      text: 'falhou',
      isError: true,
      sources: null,
    })
  })
})
