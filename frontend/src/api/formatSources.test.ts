import { describe, expect, it } from 'vitest'
import { formatSources } from './formatSources.ts'

describe('formatSources', () => {
  it('returns null when no citation arrived', () => {
    expect(formatSources([])).toBeNull()
  })

  it('uses the source name when the title is empty', () => {
    expect(
      formatSources([{ source: 'apostila.pdf', title: '', page: 2 }]),
    ).toBe('Fontes consultadas: apostila.pdf, p. 2')
  })

  it('groups pages of the same title and separates works', () => {
    expect(
      formatSources([
        { source: 'a.pdf', title: 'Apostila A', page: 10 },
        { source: 'a.pdf', title: 'Apostila A', page: 9 },
        { source: 'b.pdf', title: 'Apostila B', page: 1 },
      ]),
    ).toBe('Fontes consultadas: Apostila A, p. 9–10 · Apostila B, p. 1')
  })
})
