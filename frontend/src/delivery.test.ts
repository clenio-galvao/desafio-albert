import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

function readSources(directory: string): string {
  let collected = ''
  for (const name of readdirSync(directory)) {
    const path = join(directory, name)
    if (statSync(path).isDirectory()) {
      collected += readSources(path)
    } else if (!name.endsWith('.test.ts') && !name.endsWith('.test.tsx')) {
      collected += readFileSync(path, 'utf8')
    }
  }
  return collected
}

describe('frontend delivery', () => {
  it('keeps backend secrets out of the client source', () => {
    const source = readSources(join(import.meta.dirname, '.'))

    expect(source).not.toContain('OPENAI_API_KEY')
    expect(source).not.toContain('QDRANT_API_KEY')
  })

  it('publishes only the public API URL in the example env', () => {
    const example = readFileSync(join(import.meta.dirname, '../.env.example'), 'utf8')

    expect(example).toContain('VITE_API_BASE_URL=http://localhost:8000')
    expect(example).not.toContain('OPENAI_API_KEY')
    expect(example).not.toContain('QDRANT_API_KEY')
  })
})
