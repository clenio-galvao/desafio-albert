import { describe, expect, it } from 'vitest'
import { readApiBaseUrl } from './readApiBaseUrl.ts'

describe('readApiBaseUrl', () => {
  it('returns the configured public URL', () => {
    expect(readApiBaseUrl('http://localhost:8000')).toBe('http://localhost:8000')
  })

  it('returns an empty base when the variable is absent', () => {
    expect(readApiBaseUrl(undefined)).toBe('')
  })
})
