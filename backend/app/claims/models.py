"""SQLite tables for the ingested policy corpus. Nothing about a student is stored."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.documents.models import Base

POLICY_SEARCH_TABLE = "policy_chunks_fts"
POLICY_SEARCH_DDL = (
  f"CREATE VIRTUAL TABLE IF NOT EXISTS {POLICY_SEARCH_TABLE} USING fts5("
  "section_title, text, chunk_id UNINDEXED, document_id UNINDEXED, "
  "tokenize = 'porter unicode61')"
)
"""Keyword index over chunk text; SQLAlchemy cannot declare an FTS5 virtual table."""


class PolicyDocumentRecord(Base):
  """One ingested policy edition, keyed by its catalog identifier."""

  __tablename__ = "policy_documents"

  id: Mapped[str] = mapped_column(String(64), primary_key=True)
  sha256: Mapped[str] = mapped_column(String(64))
  page_count: Mapped[int] = mapped_column(Integer)
  chunk_count: Mapped[int] = mapped_column(Integer)
  ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PolicyChunkRecord(Base):
  """One retrievable passage of policy text with its location and vector."""

  __tablename__ = "policy_chunks"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  document_id: Mapped[str] = mapped_column(
    ForeignKey("policy_documents.id", ondelete="CASCADE"),
    index=True,
  )
  ordinal: Mapped[int] = mapped_column(Integer)
  scopes: Mapped[str] = mapped_column(String(64))
  """Space-separated product scopes; empty when it applies to every product."""
  section_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
  section_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
  page_start: Mapped[int] = mapped_column(Integer)
  page_end: Mapped[int] = mapped_column(Integer)
  page_breaks: Mapped[list[list[int]]] = mapped_column(JSON)
  """[character offset, page] pairs marking where each page starts in the text."""
  aspects: Mapped[str] = mapped_column(String(128))
  text: Mapped[str] = mapped_column(Text)
  embedding: Mapped[bytes] = mapped_column(LargeBinary)
  """Unit-length float32 vector, so a dot product is the cosine similarity."""


class PolicyDefinitionRecord(Base):
  """One term a policy defines, pointing at the chunk that defines it."""

  __tablename__ = "policy_definitions"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  document_id: Mapped[str] = mapped_column(
    ForeignKey("policy_documents.id", ondelete="CASCADE"),
    index=True,
  )
  term: Mapped[str] = mapped_column(String(80))
  term_key: Mapped[str] = mapped_column(String(80), index=True)
  chunk_id: Mapped[int] = mapped_column(ForeignKey("policy_chunks.id", ondelete="CASCADE"))
