import { formatPages } from './formatPages.ts'
import type { Citation } from './types.ts'

/** Monta o rodapé de fontes no mesmo texto da demo em HTML. */
export function formatSources(citations: readonly Citation[]): string | null {
  if (citations.length === 0) return null
  const grouped = new Map<string, number[]>()
  for (const item of citations) {
    const title = item.title || item.source
    const pages = grouped.get(title)
    if (pages) {
      pages.push(item.page)
    } else {
      grouped.set(title, [item.page])
    }
  }
  const label = [...grouped]
    .map(([title, pages]) => `${title}, p. ${formatPages(pages)}`)
    .join(' · ')
  return `Fontes consultadas: ${label}`
}
