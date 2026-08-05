from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.documents.models import Base

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = BACKEND_DIRECTORY / "data"
DATABASE_PATH = DATA_DIRECTORY / "documents.db"

# WAL needs a memory-mapped -shm file, which an SMB share cannot provide, so a
# deployment on network storage sets DELETE instead. A PRAGMA value cannot be
# bound as a parameter, so the accepted modes stay a fixed set.
_ALLOWED_JOURNAL_MODES = frozenset({"WAL", "DELETE"})
_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL")
if _JOURNAL_MODE not in _ALLOWED_JOURNAL_MODES:
  raise ValueError(f"Unsupported SQLITE_JOURNAL_MODE: {_JOURNAL_MODE}")

# The synchronous routes run in Starlette's worker threads, so one connection
# can legitimately be used from a thread other than the one that opened it.
engine = create_engine(
  f"sqlite:///{DATABASE_PATH}",
  connect_args={"check_same_thread": False},
)

SessionFactory = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _configure_connection(connection: Any, _: Any) -> None:
  """Let readers work during a write and keep foreign keys enforced."""
  cursor = connection.cursor()
  cursor.execute(f"PRAGMA journal_mode={_JOURNAL_MODE}")
  cursor.execute("PRAGMA foreign_keys=ON")
  cursor.close()


def initialize_database(database_engine: Engine = engine) -> None:
  """Create the data directory and any missing tables."""
  DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
  Base.metadata.create_all(database_engine)


def get_session() -> Iterator[Session]:
  """Provide one request-scoped session and close it when the request ends."""
  with SessionFactory() as session:
    yield session
