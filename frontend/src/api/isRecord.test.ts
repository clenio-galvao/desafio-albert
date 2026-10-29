import { describe, expect, it } from 'vitest'
import { isRecord } from './isRecord.ts'

describe('isRecord', () => {
  it('rejects a primitive', () => {
    expect(isRecord('texto')).toBe(false)
  })

  it('rejects null', () => {
    expect(isRecord(null)).toBe(false)
  })

  it('rejects an array', () => {
    expect(isRecord([])).toBe(false)
  })

  it('accepts a plain object', () => {
    expect(isRecord({ page: 1 })).toBe(true)
  })
})
