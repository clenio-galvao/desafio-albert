import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('loads models from the configured public API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ models: ['model-a'] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    render(<App />)

    expect(await screen.findByRole('option', { name: 'model-a' })).toBeInTheDocument()
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('http://api.test/v1/models')
  })
})
