/** Distingue um objeto JSON de lista, nulo e primitivo. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
