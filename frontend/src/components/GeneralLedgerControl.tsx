import { useEffect, useState } from 'react'

import { ApiError, fetchGlAccounts, selectGlAccount } from '../lib/api.ts'
import type { DocumentResponse, GeneralLedgerAccount } from '../lib/types.ts'

interface GeneralLedgerControlProps {
  document: DocumentResponse
  onSaved: (document: DocumentResponse) => void
}

interface LoadState {
  accounts: GeneralLedgerAccount[]
  failure: string | null
}

let accountsRequest: Promise<GeneralLedgerAccount[]> | null = null

function loadAccounts(): Promise<GeneralLedgerAccount[]> {
  accountsRequest ??= fetchGlAccounts()
  return accountsRequest
}

export default function GeneralLedgerControl({
  document,
  onSaved,
}: GeneralLedgerControlProps) {
  const [loadState, setLoadState] = useState<LoadState>({ accounts: [], failure: null })
  const [selectedCode, setSelectedCode] = useState(document.selected_gl_code ?? '')
  const [isSaving, setIsSaving] = useState(false)
  const [saveFailure, setSaveFailure] = useState<{ code: string; message: string } | null>(null)
  const suggestion = document.result.general_ledger
  const isDecided = document.status !== 'pending'

  useEffect(() => {
    let active = true
    void loadAccounts().then(
      (accounts) => {
        if (active) setLoadState({ accounts, failure: null })
      },
      (error: unknown) => {
        if (active) {
          setLoadState({
            accounts: [],
            failure: error instanceof ApiError ? error.message : 'Could not load GL accounts.',
          })
        }
      },
    )
    return () => {
      active = false
    }
  }, [])

  async function save(code: string): Promise<void> {
    if (code === '' || isDecided) {
      return
    }
    setIsSaving(true)
    setSaveFailure(null)
    try {
      onSaved(await selectGlAccount(document.id, code))
    } catch (error) {
      setSaveFailure(
        error instanceof ApiError
          ? { code: error.code, message: error.message }
          : { code: 'internal_error', message: 'Unexpected client error.' },
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">General ledger account</h3>
        {document.selected_gl_code !== null && (
          <span className="text-xs text-muted">Saved: {document.selected_gl_code}</span>
        )}
      </div>

      {suggestion !== null && (
        <div className="mt-3 rounded-lg bg-accent/5 p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Model suggestion</p>
          <p className="font-medium">
            {suggestion.account_code} · {suggestion.account_name}
          </p>
          <p className="text-sm text-muted">{suggestion.reason}</p>
          <button
            type="button"
            onClick={() => {
              setSelectedCode(suggestion.account_code)
              void save(suggestion.account_code)
            }}
            disabled={isSaving || isDecided}
            className="mt-3 rounded-lg border border-accent px-3 py-1.5 text-sm font-medium text-accent disabled:opacity-50"
          >
            Confirm suggestion
          </button>
        </div>
      )}

      <label className="mt-4 grid gap-1 text-sm">
        <span className="font-medium">Choose from the approved catalog</span>
        <select
          value={selectedCode}
          onChange={(event) => {
            setSelectedCode(event.target.value)
            setSaveFailure(null)
          }}
          disabled={loadState.accounts.length === 0 || isSaving || isDecided}
          className="min-w-0 rounded-lg border border-line bg-raised px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:bg-surface"
        >
          <option value="">Select an account</option>
          {loadState.accounts.map((account) => (
            <option key={account.code} value={account.code}>
              {account.code} · {account.name}
            </option>
          ))}
        </select>
      </label>

      {loadState.failure !== null && (
        <p className="mt-3 text-sm text-red-800">{loadState.failure}</p>
      )}
      {saveFailure !== null && (
        <p className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="font-medium">{saveFailure.code}</span>
          <span className="block">{saveFailure.message}</span>
        </p>
      )}

      <button
        type="button"
        onClick={() => void save(selectedCode)}
        disabled={selectedCode === '' || selectedCode === document.selected_gl_code || isSaving || isDecided}
        className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSaving ? 'Saving…' : 'Save GL account'}
      </button>
    </section>
  )
}
