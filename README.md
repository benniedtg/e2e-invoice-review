# Invoice Review

This is the clean starter for an end-to-end invoice and receipt review application. You will build a workflow for Northstar Facilities B.V. that combines Azure document extraction, deterministic finance rules, SQLite persistence, and a human review interface.

> You are on `main`, the learner starter. Active work is visible on `development`; the reviewed finished application is on `solution`.

## What is included

- The client brief and target architecture
- A fictional 13-document multilingual corpus
- Safe environment templates
- Exact dependency pins and lockfiles
- Backend and frontend project configuration

Application code is intentionally absent. The tutorial builds the backend and frontend from this starting point.

## Prerequisites

- Python 3.12 or newer
- uv
- Node.js 22 or newer
- pnpm 11

## Install

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile
```

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env` when the tutorial reaches environment configuration. The backend file contains only Azure provider configuration; the frontend file contains `VITE_API_BASE_URL`. Add real Azure values only when the provider stages require them.

## Verify the starter installation

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile
```

## Choose a branch

- `main`: clone this branch to follow the tutorial from the prepared starting point.
- `development`: inspect the public working branch and later experiments.
- `solution`: inspect the reviewed end product.

To switch to the finished application:

```bash
git switch solution
```

Start with [the client brief](docs/client-brief.md), then follow the [complete tutorial](https://learn.datalumina.com/docs/invoice-review).
