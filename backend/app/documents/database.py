from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

# Importing the claims models also registers the policy corpus tables on Base.
from app.claims.models import POLICY_SEARCH_DDL
from app.documents.keys import document_facts
from app.documents.models import Base, DocumentRecord

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = BACKEND_DIRECTORY / "data"
DATABASE_PATH = DATA_DIRECTORY / "documents.db"

# Columns added after the first release. create_all never alters an existing
# table, so a database created before them gains them, and their values, here.
_QUERY_COLUMNS = ("document_date", "total_cents", "currency", "vendor_search_key")

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
  """Create the data directory, any missing tables, and any missing columns."""
  DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
  Base.metadata.create_all(database_engine)
  with database_engine.begin() as connection:
    connection.execute(text(POLICY_SEARCH_DDL))
  if _add_query_columns(database_engine):
    _backfill_query_columns(database_engine)


def _add_query_columns(database_engine: Engine) -> bool:
  """Add the query columns an older database lacks and report whether any were."""
  table_name = DocumentRecord.__tablename__
  existing = {column["name"] for column in inspect(database_engine).get_columns(table_name)}
  missing = [
    DocumentRecord.__table__.columns[name]
    for name in _QUERY_COLUMNS
    if name not in existing
  ]
  with database_engine.begin() as connection:
    for column in missing:
      # Names and types come from the fixed model, never from input.
      column_type = column.type.compile(dialect=database_engine.dialect)
      connection.execute(
        text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column_type}")
      )
  return bool(missing)


def _backfill_query_columns(database_engine: Engine) -> None:
  """Fill new query columns from every stored result, human corrections included."""
  with Session(database_engine) as session:
    for record in session.scalars(select(DocumentRecord)).all():
      facts = document_facts(record.to_pipeline_result().document)
      for name, value in asdict(facts).items():
        setattr(record, name, value)
    session.commit()


def get_session() -> Iterator[Session]:
  """Provide one request-scoped session and close it when the request ends."""
  with SessionFactory() as session:
    yield session
