from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.claims import router as claims_router
from app.api.errors import ErrorCode, error_response, register_exception_handlers
from app.api.routes import router
from app.api.uploads import MAX_REQUEST_BYTES, OVERSIZED_MESSAGE
from app.config import load_api_settings
from app.documents.database import initialize_database
from app.documents.storage import initialize_storage

# The deployed image copies the built web interface here so one container can
# serve both the API and the pages that call it.
STATIC_DIRECTORY = Path(__file__).resolve().parents[1] / "static"


def create_app() -> FastAPI:
  """Build the Invoice Review API with its middleware and error contract."""
  app = FastAPI(title="Invoice Review API", version="0.1.0")
  initialize_database()
  initialize_storage()

  # Registered first so the later CORS middleware wraps it and keeps its
  # headers on rejected uploads.
  @app.middleware("http")
  async def limit_request_size(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
  ) -> Response:
    """Reject an oversized upload before its body is buffered."""
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > MAX_REQUEST_BYTES:
      return error_response(ErrorCode.PAYLOAD_TOO_LARGE, OVERSIZED_MESSAGE, 413)
    return await call_next(request)

  app.add_middleware(
    CORSMiddleware,
    allow_origins=list(load_api_settings().allowed_origins),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
  )

  register_exception_handlers(app)
  app.include_router(router)
  app.include_router(claims_router)

  # Mounted last so the API routes above keep their paths. Absent during local
  # development, where the web interface runs on its own dev server.
  if STATIC_DIRECTORY.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY, html=True), name="web")

  return app


app = create_app()
