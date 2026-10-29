export interface SseEvent {
  event: string
  data: unknown
}

/** Lê um quadro SSE no formato `event`/`data` emitido pela API. */
export function parseSseBlock(block: string): SseEvent {
  let event = 'message'
  let data = '{}'
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      data = line.slice('data:'.length).trim()
    }
  }
  try {
    return { event, data: JSON.parse(data) as unknown }
  } catch {
    throw new Error('Falha ao iniciar a resposta.')
  }
}

/** Separa quadros completos e conserva o restante ainda incompleto. */
export function pullSseBlocks(buffer: string): { blocks: string[]; rest: string } {
  const blocks: string[] = []
  let rest = buffer
  let boundary = rest.indexOf('\n\n')
  while (boundary >= 0) {
    const block = rest.slice(0, boundary)
    rest = rest.slice(boundary + 2)
    if (block.trim()) blocks.push(block)
    boundary = rest.indexOf('\n\n')
  }
  return { blocks, rest }
}
