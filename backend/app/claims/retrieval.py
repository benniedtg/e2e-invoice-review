"""Per-aspect hybrid retrieval over one policy edition, scoped to one product.

A single matching sentence is not enough evidence, so every service line gets its own
search for coverage, exclusions, waiting periods, limits, and claim requirements, plus the
definitions of terms those passages use. Keyword (FTS5 BM25) and vector (cosine) rankings
are fused with reciprocal-rank fusion.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.claims import repository
from app.claims.repository import StoredChunk
from app.claims.schemas import EvidenceAspect

PER_ASPECT = 3
CANDIDATES = 30
RRF_K = 60
ASPECT_BONUS = 1 / (RRF_K + 1)
"""A chunk tagged with the searched aspect gains as much as one first-place rank."""
PRODUCT_BONUS = 1 / (RRF_K + 1)
"""For what a product pays, its own clause outranks an equally similar shared one.
Exclusions, waiting periods, and claim rules are usually shared, so they get no bonus."""
_PRODUCT_ASPECTS = frozenset({EvidenceAspect.COVERAGE, EvidenceAspect.LIMITS})
MAX_DEFINITIONS = 6

type Embed = Callable[[Sequence[str]], list[list[float]]]

_ASPECT_TERMS = {
  EvidenceAspect.COVERAGE: "benefits payable cover",
  EvidenceAspect.EXCLUSIONS: "exclusions not covered benefits not payable",
  EvidenceAspect.WAITING_PERIODS: "waiting period",
  EvidenceAspect.LIMITS: "annual limit maximum benefit",
  EvidenceAspect.CLAIMS: "claims requirements time limit itemised account receipt",
}
_STOPWORDS = frozenset(
  "a an and are as at be by for from in is it of on or the to with".split()
)

# Receipts name services in everyday words; policies group them under their own terms.
_POLICY_VOCABULARY = (
  (
    r"glasses|spectacle|lens|frame|contact|optical|optometr|eye (?:test|exam)",
    "optical general treatment extras",
  ),
  (r"dent|tooth|teeth|scale|clean|filling|crown", "dental general treatment extras"),
  (
    r"physio|chiro|osteo|massage|podiatr|psycholog|counsel",
    "general treatment extras allied health",
  ),
  (
    r"\bgp\b|general practi|doctor|consult|medical centre|clinic|optometr|eye (?:test|exam)",
    "medical services out of hospital Medicare Benefits Schedule",
  ),
  (r"pharm|prescription|medicine|script|\bpbs\b", "pharmaceutical benefits PBS prescription"),
  (r"ambulance", "ambulance services"),
  (
    r"patholog|blood test|x-?ray|scan|imaging|radiolog|ultrasound",
    "pathology radiology out of hospital medical services",
  ),
)


def policy_readings(service_text: str) -> list[str]:
  """Every way a policy may classify a service, each in that policy's own words.

  An eye examination can be an optical extra or a Medicare-type medical service, so each
  reading gets its own coverage and limit search instead of one blurred query.
  """
  readings = [f"{service_text} {terms}" for terms in _policy_terms(service_text)]
  return readings or [service_text]


def expand_service_text(service_text: str) -> str:
  """Add every policy reading's words at once, for aspects that do not depend on it."""
  return " ".join([service_text, *_policy_terms(service_text)])


def _policy_terms(service_text: str) -> list[str]:
  lowered = service_text.casefold()
  return [terms for pattern, terms in _POLICY_VOCABULARY if re.search(pattern, lowered)]


@dataclass(frozen=True, slots=True)
class ServiceQuery:
  """One receipt line to search for, inside one product's terms."""

  line_index: int
  document_id: str
  scope: str | None
  service_text: str


@dataclass(frozen=True, slots=True)
class LineEvidence:
  """Retrieved passages for one line, grouped by aspect, with gaps made explicit."""

  line_index: int
  document_id: str
  passages: dict[EvidenceAspect, tuple[StoredChunk, ...]]
  missing_aspects: tuple[EvidenceAspect, ...]

  def chunks(self) -> dict[int, StoredChunk]:
    """Every distinct retrieved chunk, keyed by id."""
    return {chunk.id: chunk for group in self.passages.values() for chunk in group}


def retrieve_evidence(
  session: Session,
  embed: Embed,
  queries: Sequence[ServiceQuery],
) -> list[LineEvidence]:
  """Search every aspect for every line with one embeddings request."""
  searches: list[tuple[ServiceQuery, EvidenceAspect, str]] = []
  for query in queries:
    for aspect in _ASPECT_TERMS:
      readings = (
        policy_readings(query.service_text)
        if aspect in _PRODUCT_ASPECTS
        else [expand_service_text(query.service_text)]
      )
      if aspect == EvidenceAspect.COVERAGE:
        # A product's general clause for a reading ("Medical Services Payments") shares few
        # words with the receipt line, whose own words pull in item tables instead.
        readings += _policy_terms(query.service_text)
      searches.extend(
        (query, aspect, f"{reading} {_ASPECT_TERMS[aspect]}") for reading in readings
      )
  vectors = embed([search_text for _, _, search_text in searches])
  candidates: dict[tuple[str, str | None], list[StoredChunk]] = {}
  found: dict[int, dict[EvidenceAspect, tuple[StoredChunk, ...]]] = defaultdict(dict)

  for (query, aspect, search_text), vector in zip(searches, vectors, strict=True):
    key = (query.document_id, query.scope)
    if key not in candidates:
      candidates[key] = repository.scoped_chunks(session, query.document_id, query.scope)
    ranked = _rank(
      session,
      candidates[key],
      query.document_id,
      search_text,
      vector,
      aspect,
      query.scope,
      PER_ASPECT * 2,
    )
    # Each reading of the service adds its own best passages, not repeats of another's.
    earlier = found[query.line_index].get(aspect, ())
    unseen = [chunk for chunk in ranked if all(chunk.id != seen.id for seen in earlier)]
    found[query.line_index][aspect] = earlier + tuple(unseen[:PER_ASPECT])

  evidence: list[LineEvidence] = []
  for query in queries:
    passages = found[query.line_index]
    definitions = _definitions(
      session,
      query.document_id,
      candidates[(query.document_id, query.scope)],
      passages,
    )
    passages[EvidenceAspect.DEFINITIONS] = definitions
    missing = tuple(
      aspect
      for aspect, chunks in passages.items()
      if not any(aspect in chunk.aspects for chunk in chunks)
      and not (aspect == EvidenceAspect.DEFINITIONS and chunks)
    )
    evidence.append(LineEvidence(
      line_index=query.line_index,
      document_id=query.document_id,
      passages=dict(passages),
      missing_aspects=missing,
    ))
  return evidence


def match_query(search_text: str) -> str:
  """Build an FTS5 query of quoted alphanumeric terms, so no input is FTS syntax."""
  terms: list[str] = []
  for term in re.findall(r"[a-z0-9]+", search_text.casefold()):
    if term not in _STOPWORDS and term not in terms and (len(term) > 1 or term.isdigit()):
      terms.append(term)
  return " OR ".join(f'"{term}"' for term in terms[:16])


def _rank(
  session: Session,
  candidates: Sequence[StoredChunk],
  document_id: str,
  search_text: str,
  vector: Sequence[float],
  aspect: EvidenceAspect,
  scope: str | None,
  limit: int,
) -> tuple[StoredChunk, ...]:
  allowed = {chunk.id: chunk for chunk in candidates}
  if not allowed:
    return ()
  query = match_query(search_text)
  keyword_ids = [
    chunk_id
    for chunk_id in (
      repository.keyword_ranking(session, document_id, query, CANDIDATES * 3) if query else []
    )
    if chunk_id in allowed
  ][:CANDIDATES]
  by_similarity = sorted(
    candidates,
    key=lambda chunk: math.sumprod(chunk.vector, vector),
    reverse=True,
  )[:CANDIDATES]

  scores: dict[int, float] = defaultdict(float)
  for rank, chunk_id in enumerate(keyword_ids):
    scores[chunk_id] += 1 / (RRF_K + rank + 1)
  for rank, chunk in enumerate(by_similarity):
    scores[chunk.id] += 1 / (RRF_K + rank + 1)
  for chunk_id in scores:
    if aspect in allowed[chunk_id].aspects:
      scores[chunk_id] += ASPECT_BONUS
    if aspect in _PRODUCT_ASPECTS and scope is not None and scope in allowed[chunk_id].scopes:
      scores[chunk_id] += PRODUCT_BONUS
  best = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:limit]
  return tuple(allowed[chunk_id] for chunk_id in best)


def _definitions(
  session: Session,
  document_id: str,
  candidates: Sequence[StoredChunk],
  passages: dict[EvidenceAspect, tuple[StoredChunk, ...]],
) -> tuple[StoredChunk, ...]:
  """Pull in the definitions of terms the coverage and exclusion passages use."""
  text = " ".join(
    chunk.text
    for aspect in (EvidenceAspect.COVERAGE, EvidenceAspect.EXCLUSIONS)
    for chunk in passages.get(aspect, ())
  ).casefold()
  allowed = {chunk.id: chunk for chunk in candidates}
  already = {chunk.id for group in passages.values() for chunk in group}
  picked: list[StoredChunk] = []
  for term_key, chunk_id in repository.definitions_for(session, document_id):
    if chunk_id in already or chunk_id not in allowed:
      continue
    if re.search(rf"\b{re.escape(term_key)}\b", text):
      already.add(chunk_id)
      picked.append(allowed[chunk_id])
      if len(picked) == MAX_DEFINITIONS:
        break
  return tuple(picked)
