import { API_BASE_URL } from './env.ts'
import type {
  CorrectionEmailDraft,
  DocumentCorrections,
  DocumentResponse,
  DocumentSummary,
  ErrorCode,
  GeneralLedgerAccount,
  StepEvent,
} from './types.ts'

/** The backend's fixed limit in `backend/app/api/uploads.py`. */
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024

/** The types the backend detects from a document's leading bytes. */
export const ACCEPTED_MIME_TYPES = ['application/pdf', 'image/png', 'image/jpeg'] as const

/** One failed request carrying the backend's stable error code. */
export class ApiError extends Error {
  readonly code: ErrorCode

  constructor(code: ErrorCode, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

function readErrorBody(body: unknown): ApiError {
  if (typeof body === 'object' && body !== null && 'error' in body) {
    const detail = (body as { error: unknown }).error
    if (typeof detail === 'object' && detail !== null && 'code' in detail && 'message' in detail) {
      const { code, message } = detail as { code: unknown; message: unknown }
      if (typeof code === 'string' && typeof message === 'string') {
        return new ApiError(code as ErrorCode, message)
      }
    }
  }
  return new ApiError('internal_error', 'The server returned an unreadable error.')
}

async function request<Payload>(path: string, init: RequestInit): Promise<Payload> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch {
    throw new ApiError('network_error', `Cannot reach the API at ${API_BASE_URL}.`)
  }

  if (response.ok && response.status === 204) {
    return undefined as Payload
  }

  const payload: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw readErrorBody(payload)
  }

  return payload as Payload
}

/** Upload one document and run the classification pipeline over it. */
export function processDocument(file: File, signal?: AbortSignal): Promise<DocumentResponse> {
  const body = new FormData()
  body.append('file', file)

  return request<DocumentResponse>('/api/documents/process', {
    method: 'POST',
    body,
    signal,
  })
}

/** List the review history, newest first. */
export function listDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>('/api/documents', { method: 'GET' })
}

/** Load one stored document with its full pipeline result. */
export function fetchDocument(id: string): Promise<DocumentResponse> {
  return request<DocumentResponse>(`/api/documents/${encodeURIComponent(id)}`, { method: 'GET' })
}

/** Resolve the trusted source endpoint from an encoded generated identifier. */
export function sourceDocumentUrl(id: string): string {
  return `${API_BASE_URL}/api/documents/${encodeURIComponent(id)}/file`
}

/** Load the fixed Northstar account catalog. */
export function fetchGlAccounts(): Promise<GeneralLedgerAccount[]> {
  return request<GeneralLedgerAccount[]>('/api/gl-accounts', { method: 'GET' })
}

/** Save only explicit changed correction fields and return recomputed server state. */
export function saveCorrections(
  id: string,
  body: DocumentCorrections,
): Promise<DocumentResponse> {
  return request<DocumentResponse>(
    `/api/documents/${encodeURIComponent(id)}/corrections`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

/** Persist one explicit catalog selection without promoting the model suggestion. */
export function selectGlAccount(
  id: string,
  accountCode: string,
): Promise<DocumentResponse> {
  return request<DocumentResponse>(
    `/api/documents/${encodeURIComponent(id)}/gl-selection`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_code: accountCode }),
    },
  )
}

/** Save one final human decision and return authoritative server state. */
export function decideDocument(
  id: string,
  decision: 'approved' | 'rejected',
): Promise<DocumentResponse> {
  return request<DocumentResponse>(
    `/api/documents/${encodeURIComponent(id)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    },
  )
}

/** Generate one copy-only supplier correction draft on demand. */
export function draftCorrectionEmail(id: string): Promise<CorrectionEmailDraft> {
  return request<CorrectionEmailDraft>(
    `/api/documents/${encodeURIComponent(id)}/correction-email`,
    { method: 'POST' },
  )
}

/** Permanently remove one stored local record and its trusted source. */
export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

interface StreamFrame {
  event: string
  data: unknown
}

/** Parse one `event:`/`data:` block into its name and payload. */
function readFrame(frame: string): StreamFrame | null {
  let event = ''
  let data = ''

  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      data += line.slice('data:'.length).trim()
    }
  }

  if (event === '' || data === '') {
    return null
  }

  try {
    return { event, data: JSON.parse(data) as unknown }
  } catch {
    return null
  }
}

/**
 * Upload one document and report each pipeline stage as the server reaches it.
 *
 * A failure before the stream starts arrives as the ordinary JSON envelope with
 * its real status. Once frames are flowing the status is already 200, so a
 * later failure arrives as an `error` frame instead.
 */
export async function streamDocument(
  file: File,
  onStep: (event: StepEvent) => void,
): Promise<DocumentResponse> {
  const body = new FormData()
  body.append('file', file)

  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}/api/documents/process/stream`, {
      method: 'POST',
      body,
    })
  } catch {
    throw new ApiError('network_error', `Cannot reach the API at ${API_BASE_URL}.`)
  }

  if (!response.ok) {
    throw readErrorBody(await response.json().catch(() => null))
  }

  if (response.body === null) {
    throw new ApiError('internal_error', 'The server returned an empty stream.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: DocumentResponse | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const frame = readFrame(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)

      if (frame !== null) {
        if (frame.event === 'step') {
          onStep(frame.data as StepEvent)
        } else if (frame.event === 'result') {
          result = frame.data as DocumentResponse
        } else if (frame.event === 'error') {
          await reader.cancel()
          throw readErrorBody(frame.data)
        }
      }

      boundary = buffer.indexOf('\n\n')
    }
  }

  if (result === null) {
    throw new ApiError('internal_error', 'The stream ended without a result.')
  }

  return result
}
