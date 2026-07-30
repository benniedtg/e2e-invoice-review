# Build-along guide

The complete guided build lives at <https://learn.datalumina.com/docs/invoice-review>. This local guide records the first checkpoint represented by the `main` branch.

## Starter outcome

The repository installs reproducibly, starts a minimal FastAPI service and React interface, and includes the business brief plus fictional source documents.

## Why this boundary exists

The starter removes the completed workflow while preserving every prerequisite needed to build it. You begin with the user, the source documents, and explicit service boundaries instead of reverse-engineering a finished application.

## Commands

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile

cd ..
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./scripts/dev.sh --check
./scripts/dev.sh
```

## Important locations

- `docs/client-brief.md`: the recurring finance problem and definition of done
- `docs/architecture.md`: the intended boundaries and data flow
- `samples/`: the fictional evaluation corpus and manifest
- `backend/app/main.py`: the initial API boundary
- `frontend/src/App.tsx`: the initial interface boundary

## What you should observe

- `GET http://localhost:8000/health` returns `{"status":"ok"}`.
- `http://localhost:5173` shows the Invoice Review starter screen.
- No Azure request occurs at this checkpoint.

## Checkpoint

- [ ] Locked backend and frontend installs succeed.
- [ ] Backend lint passes.
- [ ] Frontend type-check, lint, and production build pass.
- [ ] `./scripts/dev.sh --check` reports that Invoice Review is ready to start.
- [ ] The health endpoint and starter screen load locally.

Continue with the [online tutorial](https://learn.datalumina.com/docs/invoice-review).

## Document Intelligence invoice and receipt CLI

### Outcome

The backend can send one local fictional PDF or image to Azure AI Document Intelligence's `prebuilt-invoice` or `prebuilt-receipt` model. It saves both the complete provider result and a normalized Pydantic invoice or receipt.

### Why

This narrow command-line checkpoint keeps the provider payload visible while introducing the provider-independent data shape used by later review work. Azure SDK types remain inside `app/providers/azure_document_intelligence.py`; `app/schemas/invoice/` and `app/schemas/receipt/` contain strict normalized models with typed values, original OCR content, and confidence.

`DocumentIntelligenceSettings` lives in `app/config.py` and keeps the endpoint and key required at runtime. Its no-argument constructor has a narrow Pylance `reportCallIssue` suppression because `BaseSettings` supplies those fields from `.env`, which static constructor inference cannot see.

### Command

Store the rotated endpoint and key in ignored `backend/.env`, then run one invoice and one receipt experiment:

```bash
cd backend
uv run --locked --no-sync python app/services/document_intelligence_services.py \
  --document-type invoice \
  ../samples/generated/09-nl-missing-po.pdf

uv run --locked --no-sync python app/services/document_intelligence_services.py \
  --document-type receipt \
  ../samples/generated/13-nl-fuel-receipt.png
```

These commands perform two analyze requests across two pages. They are free while the Document Intelligence F0 allowance remains; S0 is billed per analyzed page. No project-owned cloud resource is created. The ignored observation files remain available until `backend/json_extracted/` is deleted locally.

Map the previously saved happy-invoice payload without another Azure request:

```bash
uv run --locked --no-sync python -c '
import json
from pathlib import Path
from app.providers.azure_document_intelligence import map_document
from app.schemas import DocumentType

raw = json.loads(Path("json_extracted/01-en-happy-classic.json").read_text())
document = map_document(raw, DocumentType.INVOICE)
assert len(document.items) == 4
assert len(document.tax_details) == 1
print("offline invoice mapping: passed")
'
```

After observation, remove only the two live experiment outputs with:

```bash
rm -f \
  json_extracted/09-nl-missing-po.json \
  json_extracted/09-nl-missing-po.normalized.json \
  json_extracted/13-nl-fuel-receipt.json \
  json_extracted/13-nl-fuel-receipt.normalized.json
```

### Observable result

The terminal prints two saved paths per document. `<stem>.json` contains the complete Azure payload. `<stem>.normalized.json` contains the strict Pydantic model with snake-case fields, typed dates and decimal money, OCR evidence, and confidence.

The missing-PO invoice has `purchase_order: null`. The Dutch fuel receipt uses `document_type: "receipt"` and maps merchant, transaction, item, tax, and total fields independently from the invoice schema. Its `payments` list is empty because Azure returned no `Payments` field for this sample.

### Checkpoint

- [ ] `uv run --locked --no-sync ruff check app` passes.
- [ ] `--help` succeeds without an Azure request.
- [ ] A missing file fails locally with a concise error.
- [ ] The saved happy invoice maps offline with four line items and one tax detail.
- [ ] The missing-PO invoice saves valid raw and normalized invoice JSON.
- [ ] The fuel receipt saves valid raw and normalized receipt JSON.

## Azure OpenAI text prompt CLI

### Outcome

The backend can send one text prompt to the Azure OpenAI Responses API and print the returned text. This first checkpoint deliberately accepts text only; invoice and receipt input remain outside the service until the text flow is approved.

### Why

The narrow command proves endpoint, API-key, deployment, and Responses API connectivity before document review is introduced. Azure OpenAI SDK types remain inside `app/providers/azure_openai.py`, while `app/services/azure_openai_service.py` handles only command-line input and output.

`AzureOpenAISettings` loads `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` from ignored `backend/.env`. The deployment name `gpt-5.6-terra` is intentionally fixed in the provider adapter instead of being configurable through the environment.

### Command

Store the endpoint and a rotated API key in ignored `backend/.env`, then run one short experiment:

```bash
cd backend
uv run --locked --no-sync python app/services/azure_openai_service.py \
  "What is the capital of Vietnam? Reply with only the city name."
```

This command makes one token-metered Azure OpenAI request. It sets `store=False`, so the application does not request response storage. It creates no project-owned cloud resource and writes no local output file; there is nothing to clean up after the experiment.

The endpoint must use HTTPS. It can be the Azure resource root, a Foundry project endpoint ending in `/api/projects/<project-name>`, or the full `/openai/v1/` base URL. The provider adapter normalizes every supported form using the routes in the [Microsoft Foundry Responses API documentation](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject).

### Observable result

The terminal prints the generated text with an `answer:` prefix:

```text
answer: Hanoi
```

Blank prompts and invalid or missing configuration fail locally with a concise error. Provider error details and secrets are not printed.

### Checkpoint

- [ ] `uv run --locked --no-sync ruff check app` passes.
- [ ] `azure_openai_service.py --help` succeeds without an Azure request.
- [ ] A blank prompt fails without an Azure request.
- [ ] An invalid endpoint is rejected without exposing its value or the API key.
- [ ] One short live text prompt prints a non-empty `answer:` response.
