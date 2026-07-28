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

## Document Intelligence invoice CLI

### Outcome

The backend can send one local fictional PDF or image invoice to Azure AI Document Intelligence's `prebuilt-invoice` model and save the complete provider result as formatted JSON.

### Why

This narrow command-line checkpoint makes the provider data model visible before normalization, persistence, policy, or HTTP orchestration is introduced. It also keeps the first paid or quota-limited provider interaction explicit.

`DocumentIntelligenceSettings` keeps the endpoint and key required at runtime. Its no-argument constructor has a narrow Pylance `reportCallIssue` suppression because `BaseSettings` supplies those fields from `.env`, which static constructor inference cannot see.

### Command

Store the rotated endpoint and key in ignored `backend/.env`, then run one fictional sample:

```bash
cd backend
uv run --locked --no-sync python app/services/document_intelligence_services.py \
  ../samples/generated/01-en-happy-classic.pdf
```

This performs one analyze request for one page. It is free while the Document Intelligence F0 allowance remains; S0 is billed per analyzed page. The command creates `backend/json_extracted/01-en-happy-classic.json`, overwriting that file when the same sample is processed again. The ignored output directory can be deleted when observation is complete; no project-owned cloud resource is created.

### Observable result

The terminal prints the saved file path. Opening that file shows an indented JSON object with `modelId` set to `prebuilt-invoice`, plus the complete `pages`, `documents`, extracted invoice fields, values, and confidence metadata returned by Azure.

### Checkpoint

- [ ] `uv run --locked --no-sync ruff check app` passes.
- [ ] `--help` succeeds without an Azure request.
- [ ] A missing file fails locally with a concise error.
- [ ] One fictional sample saves complete `prebuilt-invoice` JSON under `backend/json_extracted/`.
