/** Usa a URL pública configurada e, sem ela, caminhos relativos. */
export function readApiBaseUrl(value: string | undefined): string {
  return value ?? ''
}
