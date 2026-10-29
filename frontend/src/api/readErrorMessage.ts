/** Expõe a mensagem de uma falha e esconde valores que não são erro. */
export function readErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message
  return fallback
}
