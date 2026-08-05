# syntax=docker/dockerfile:1

# Build the web interface against its own origin, so the API it calls is the
# same container that serves these files.
FROM node:22-slim AS web
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV VITE_API_BASE_URL=""
RUN pnpm build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app/backend
ENV UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock ./
# --frozen, not --locked: the project's relative `exclude-newer` resolves to a
# fresh timestamp on every build, which would always read as a stale lockfile.
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY --from=web /build/dist ./static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
