# Document Intelligence invoice CLI design

## Outcome

Provide a minimal command-line surface in
`backend/app/services/document_intelligence_services.py` that submits one local invoice to
Azure AI Document Intelligence's `prebuilt-invoice` model and prints the complete analysis
result as formatted JSON.

## Invocation

From `backend/`, the learner supplies one local PDF, PNG, JPG, or JPEG path:

```bash
uv run --locked --no-sync python app/services/document_intelligence_services.py \
  ../samples/generated/01-en-happy-classic.pdf
```

The command exits with status zero after printing the complete `AnalyzeResult` data model.
Invalid local input, missing configuration, or a provider failure prints a concise message to
standard error and exits nonzero.

## Configuration and credential safety

The CLI uses the already-pinned `pydantic-settings` package to read
`AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY` from
`backend/.env`. Credentials are never embedded in Python or printed. The tracked
`backend/.env.example` contains placeholders only.

The credential currently present in `backend/.env.example` must be rotated in Azure and moved
to ignored `backend/.env` before a live request is made.

## Components

All behavior stays in the requested service file:

- A small settings model validates that the endpoint and key are present.
- A file-boundary function resolves the supplied path and rejects missing files, directories,
  unsupported suffixes, empty files, and files larger than the product's 4 MB limit.
- An analysis function creates a synchronous `DocumentIntelligenceClient`, streams the local
  document to `begin_analyze_document`, selects `prebuilt-invoice`, and waits for the poller.
- A serialization function converts the complete SDK result with `AnalyzeResult.as_dict()` and
  formats it with `json.dumps`; `default=str` preserves values such as dates without reducing
  the returned structure.
- A `main()` function owns argument parsing, user-facing errors, printing, and exit status.

The file is an intentionally narrow learning surface. The later application workflow will move
Azure SDK types into `backend/app/providers/azure_document_intelligence.py`, as required by the
target architecture.

## Data flow

1. The learner passes a local invoice path.
2. The CLI validates local configuration and the file boundary.
3. The Azure SDK uploads the document bytes to `prebuilt-invoice`.
4. The CLI waits for Azure's long-running analysis operation.
5. The complete result is converted to plain Python data and printed as indented JSON.

No result is written to disk or stored in SQLite.

## Error handling

Expected local failures receive direct, actionable messages. Azure SDK exceptions are caught at
the CLI boundary and summarized without exposing the credential or dumping a traceback during
normal use. Unexpected programming errors remain visible during development rather than being
silently converted into provider failures.

## Verification

The project explicitly excludes committed automated tests. Verification is demo-oriented:

1. Run Ruff against `app` and `scripts`.
2. Confirm `--help` succeeds without contacting Azure.
3. Confirm an invalid local path exits nonzero without contacting Azure.
4. After the credential is secured, run one fictional one-page sample through the live Azure
   resource and inspect the emitted JSON for the model ID, document collection, fields, pages,
   and confidence values.

The single live check consumes one Document Intelligence analyze transaction and one analyzed
page. It is free while the documented F0 monthly allowance remains; on S0 it is billable by
page. Azure retains no project artifact that this CLI needs to clean up.

## Teaching guide update

`docs/build-along.md` will be updated in the implementation slice with the outcome, rationale,
exact CLI command, expected observable result, cost note, and checkpoint.
