import { describe, expect, it } from 'vitest'
import { formatPages } from './formatPages.ts'

describe('formatPages', () => {
  it('returns an empty label when there are no pages', () => {
    expect(formatPages([])).toBe('')
  })

  it('prints a single page', () => {
    expect(formatPages([3])).toBe('3')
  })

  it('collapses a consecutive range', () => {
    expect(formatPages([10, 9])).toBe('9–10')
  })

  it('keeps a gap between ranges', () => {
    expect(formatPages([1, 3, 4, 3])).toBe('1, 3–4')
  })
})
