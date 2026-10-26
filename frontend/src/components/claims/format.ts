import type { ClaimCitation } from '../../lib/types.ts'

/** Name a passage as `where()` in `backend/app/claims/evaluation.py` does. */
export function describeCitation(citation: ClaimCitation): string {
  const { section_number: number, section_title: title, page } = citation
  if (number !== null && number.startsWith('Schedule')) return `${number}, page ${page}`
  if (number !== null) return `Section ${number}, page ${page}`
  if (title !== null) return `“${title}”, page ${page}`
  return `Page ${page}`
}

/** Dollars to the cent, whether the server sent "75" or "75.00". */
export function money(value: string): string {
  return `$${Number(value).toFixed(2)}`
}
