"""SQLite access for the policy corpus: ingest writes and retrieval reads."""

from __future__ import annotations

import math
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.claims.knowledge import ChunkDraft
from app.claims.models import (
  POLICY_SEARCH_TABLE,
  PolicyChunkRecord,
  PolicyDefinitionRecord,
  PolicyDocumentRecord,
)
from app.claims.schemas import EvidenceAspect


@dataclass(frozen=True, slots=True)
class StoredChunk:
  """One stored chunk loaded for scoring, with its unit-length vector."""

  id: int
  document_id: str
  scopes: frozenset[str]
  section_number: str | None
  section_title: str | None
  page_start: int
  page_end: int
  page_breaks: tuple[tuple[int, int], ...]
  aspects: frozenset[EvidenceAspect]
  text: str
  vector: array

  def page_of(self, offset: int) -> int:
    """Return the page a character offset in this chunk's text is printed on."""
    page = self.page_start
    for start, number in self.page_breaks:
      if start <= offset:
        page = number
    return page


def ingested_documents(session: Session) -> dict[str, PolicyDocumentRecord]:
  """Map each ingested policy edition's identifier to its record."""
  return {record.id: record for record in session.scalars(select(PolicyDocumentRecord))}


def replace_document(
  session: Session,
  *,
  document_id: str,
  sha256: str,
  page_count: int,
  chunks: Sequence[ChunkDraft],
  vectors: Sequence[Sequence[float]],
  definitions: Sequence[tuple[str, int]],
) -> None:
  """Atomically replace one edition's chunks, vectors, keyword index, and definitions."""
  if len(chunks) != len(vectors):
    raise ValueError("Every chunk needs exactly one vector.")
  session.execute(
    text(f"DELETE FROM {POLICY_SEARCH_TABLE} WHERE document_id = :document_id"),
    {"document_id": document_id},
  )
  session.execute(
    delete(PolicyDefinitionRecord).where(PolicyDefinitionRecord.document_id == document_id)
  )
  session.execute(delete(PolicyChunkRecord).where(PolicyChunkRecord.document_id == document_id))
  session.execute(delete(PolicyDocumentRecord).where(PolicyDocumentRecord.id == document_id))
  session.add(PolicyDocumentRecord(
    id=document_id,
    sha256=sha256,
    page_count=page_count,
    chunk_count=len(chunks),
    ingested_at=datetime.now(UTC),
  ))
  session.flush()

  records: list[PolicyChunkRecord] = []
  for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
    record = PolicyChunkRecord(
      document_id=document_id,
      ordinal=ordinal,
      scopes=" ".join(sorted(chunk.scopes)),
      section_number=chunk.section_number,
      section_title=chunk.section_title,
      page_start=chunk.page_start,
      page_end=chunk.page_end,
      page_breaks=[list(pair) for pair in chunk.page_breaks],
      aspects=" ".join(aspect.value for aspect in chunk.aspects),
      text=chunk.text,
      embedding=_unit_vector(vector).tobytes(),
    )
    session.add(record)
    records.append(record)
  session.flush()

  for chunk, record in zip(chunks, records, strict=True):
    session.execute(
      text(
        f"INSERT INTO {POLICY_SEARCH_TABLE} (section_title, text, chunk_id, document_id) "
        "VALUES (:section_title, :text, :chunk_id, :document_id)"
      ),
      {
        "section_title": chunk.heading_path,
        "text": chunk.text,
        "chunk_id": record.id,
        "document_id": document_id,
      },
    )
  for term, chunk_index in definitions:
    session.add(PolicyDefinitionRecord(
      document_id=document_id,
      term=term,
      term_key=term.casefold(),
      chunk_id=records[chunk_index].id,
    ))
  session.commit()


def scoped_chunks(session: Session, document_id: str, scope: str | None) -> list[StoredChunk]:
  """Load one edition's chunks that apply to a product scope (all of them for None)."""
  statement = select(PolicyChunkRecord).where(PolicyChunkRecord.document_id == document_id)
  chunks: list[StoredChunk] = []
  for record in session.scalars(statement):
    scopes = frozenset(record.scopes.split())
    if scope is not None and scopes and scope not in scopes:
      continue
    chunks.append(_stored(record))
  return chunks


def chunks_by_id(session: Session, chunk_ids: Sequence[int]) -> dict[int, StoredChunk]:
  """Load specific chunks, for example to re-verify quotes the browser sent back."""
  if not chunk_ids:
    return {}
  statement = select(PolicyChunkRecord).where(PolicyChunkRecord.id.in_(set(chunk_ids)))
  return {record.id: _stored(record) for record in session.scalars(statement)}


def keyword_ranking(
  session: Session,
  document_id: str,
  match_query: str,
  limit: int,
) -> list[int]:
  """Rank one edition's chunks for an FTS5 query, best first."""
  rows = session.execute(
    text(
      f"SELECT chunk_id FROM {POLICY_SEARCH_TABLE} "
      f"WHERE {POLICY_SEARCH_TABLE} MATCH :query AND document_id = :document_id "
      f"ORDER BY bm25({POLICY_SEARCH_TABLE}) LIMIT :limit"
    ),
    {"query": match_query, "document_id": document_id, "limit": limit},
  )
  return [int(row[0]) for row in rows]


def definitions_for(session: Session, document_id: str) -> list[tuple[str, int]]:
  """List (term key, defining chunk id) for one edition."""
  statement = select(PolicyDefinitionRecord.term_key, PolicyDefinitionRecord.chunk_id).where(
    PolicyDefinitionRecord.document_id == document_id
  )
  return [(term_key, chunk_id) for term_key, chunk_id in session.execute(statement)]


def _unit_vector(values: Sequence[float]) -> array:
  vector = array("f", values)
  norm = math.sqrt(math.sumprod(vector, vector))
  if norm == 0:
    raise ValueError("An embedding vector cannot be all zeros.")
  return array("f", (value / norm for value in vector))


def _stored(record: PolicyChunkRecord) -> StoredChunk:
  vector = array("f")
  vector.frombytes(record.embedding)
  return StoredChunk(
    id=record.id,
    document_id=record.document_id,
    scopes=frozenset(record.scopes.split()),
    section_number=record.section_number,
    section_title=record.section_title,
    page_start=record.page_start,
    page_end=record.page_end,
    page_breaks=tuple((int(start), int(page)) for start, page in record.page_breaks),
    aspects=frozenset(EvidenceAspect(value) for value in record.aspects.split()),
    text=record.text,
    vector=vector,
  )
