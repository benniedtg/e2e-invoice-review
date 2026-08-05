/** The only place browser code reads Vite environment values. */

function readApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL

  if (typeof configured !== 'string') {
    throw new Error('VITE_API_BASE_URL is missing. Copy .env.example to .env.')
  }

  const trimmed = configured.trim()

  // An empty value means the API shares this page's origin, which is how the
  // deployed single-container image serves it.
  if (trimmed === '') {
    return ''
  }

  try {
    new URL(trimmed)
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid URL: ${trimmed}`)
  }

  return trimmed.replace(/\/+$/, '')
}

export const API_BASE_URL = readApiBaseUrl()
