import { describe, expect, it } from 'vitest'
import { parseSseBlock, pullSseBlocks } from './parseSse.ts'

describe('parseSseBlock', () => {
  it('reads the event name and the JSON payload', () => {
    expect(parseSseBlock('event: token\ndata: {"content":"Olá"}\nid: 1')).toEqual({
      event: 'token',
      data: { content: 'Olá' },
    })
  })

  it('defaults a block without event or data', () => {
    expect(parseSseBlock('id: 1')).toEqual({ event: 'message', data: {} })
  })

  it('rejects a payload that is not JSON', () => {
    expect(() => parseSseBlock('event: token\ndata: {')).toThrow(
      'Falha ao iniciar a resposta.',
    )
  })
})

describe('pullSseBlocks', () => {
  it('keeps an incomplete frame in the remainder', () => {
    expect(pullSseBlocks('event: token\ndata: {}')).toEqual({
      blocks: [],
      rest: 'event: token\ndata: {}',
    })
  })

  it('returns a complete frame and the next partial one', () => {
    expect(pullSseBlocks('event: token\ndata: {}\n\nevent: done')).toEqual({
      blocks: ['event: token\ndata: {}'],
      rest: 'event: done',
    })
  })

  it('skips an empty frame', () => {
    expect(pullSseBlocks('event: token\ndata: {}\n\n\n\n')).toEqual({
      blocks: ['event: token\ndata: {}'],
      rest: '',
    })
  })
})
