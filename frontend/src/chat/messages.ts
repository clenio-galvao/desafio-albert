export const MESSAGE_MAX_LENGTH = 4000

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  isError: boolean
  sources: string | null
}

/** Troca a bolha vazia pelo erro, ou acrescenta outra se o texto já começou. */
export function appendStreamError(
  messages: readonly ChatMessage[],
  answerId: number,
  text: string,
  nextId: number,
): ChatMessage[] {
  const answer = messages.find((item) => item.id === answerId)
  if (answer === undefined) return [...messages]
  if (answer.text) {
    return [
      ...messages,
      { id: nextId, role: 'assistant', text, isError: true, sources: null },
    ]
  }
  return messages.map((item) =>
    item.id === answerId ? { ...item, text, isError: true } : item,
  )
}
