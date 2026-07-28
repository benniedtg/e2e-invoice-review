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
