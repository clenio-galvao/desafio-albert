import { describe, expect, it } from 'vitest'
import { readErrorMessage } from './readErrorMessage.ts'

describe('readErrorMessage', () => {
  it('returns the message of an Error', () => {
    expect(readErrorMessage(new Error('modelo inválido'), 'fallback')).toBe(
      'modelo inválido',
    )
  })

  it('falls back when the Error message is blank', () => {
    expect(readErrorMessage(new Error('  '), 'fallback')).toBe('fallback')
  })

  it('falls back when the thrown value is not an Error', () => {
    expect(readErrorMessage('falhou', 'fallback')).toBe('fallback')
  })
})
