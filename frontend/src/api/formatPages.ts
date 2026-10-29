/** Agrupa páginas consecutivas para a citação caber numa linha. */
export function formatPages(pages: readonly number[]): string {
  const sorted = [...new Set(pages)].sort((left, right) => left - right)
  const ranges: Array<[number, number]> = []
  for (const page of sorted) {
    const last = ranges.at(-1)
    if (last && page === last[1] + 1) {
      last[1] = page
    } else {
      ranges.push([page, page])
    }
  }
  return ranges
    .map(([start, end]) => (start === end ? `${start}` : `${start}–${end}`))
    .join(', ')
}
