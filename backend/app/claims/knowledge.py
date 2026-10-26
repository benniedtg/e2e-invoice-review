"""Turn one policy PDF into section-aware, product-scoped, aspect-tagged chunks.

Each insurer numbers its rules differently, so section detection follows the
document's catalog layout. Everything here is pure except reading the PDF.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.claims.catalog import DocumentLayout
from app.claims.schemas import EvidenceAspect

CHUNK_TARGET_WORDS = 260
"""Close a chunk at the first line boundary after this many words."""

_WHITESPACE = re.compile(r"\s+")
_PAGE_NUMBER = re.compile(r"^\d{1,3}(\s+\d{1,3})?$")
_TABLE_OF_CONTENTS = re.compile(r"\.{4,}")


@dataclass(frozen=True, slots=True)
class PageLine:
  """One non-empty line of extracted text and the page it is printed on."""

  page: int
  text: str


@dataclass(slots=True)
class Section:
  """Consecutive lines under one heading, within one product scope."""

  number: str | None
  title: str | None
  parent: str | None
  scopes: frozenset[str]
  lines: list[PageLine] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ChunkDraft:
  """One chunk ready to embed and store."""

  section_number: str | None
  section_title: str | None
  heading_path: str
  scopes: frozenset[str]
  page_start: int
  page_end: int
  page_breaks: tuple[tuple[int, int], ...]
  aspects: tuple[EvidenceAspect, ...]
  text: str


def read_pdf_lines(path: Path) -> list[PageLine]:
  """Extract each page's lines, dropping page numbers and contents-page leaders."""
  from pypdf import PdfReader

  lines: list[PageLine] = []
  for number, page in enumerate(PdfReader(path).pages, start=1):
    for raw in (page.extract_text() or "").splitlines():
      text = _WHITESPACE.sub(" ", raw).strip()
      if text and not _PAGE_NUMBER.match(text) and not _TABLE_OF_CONTENTS.search(text):
        lines.append(PageLine(page=number, text=text))
  return lines


def split_sections(lines: Sequence[PageLine], layout: DocumentLayout) -> list[Section]:
  """Group lines under the headings this layout uses, dropping contents pages."""
  splitter = _SPLITTERS[layout]
  return [
    section
    for section in splitter(lines)
    if section.lines and (section.title or "").casefold() not in _CONTENTS_TITLES
  ]


def chunk_sections(sections: Iterable[Section]) -> list[ChunkDraft]:
  """Cut sections into chunks of about CHUNK_TARGET_WORDS, never across sections."""
  chunks: list[ChunkDraft] = []
  for section in sections:
    heading_path = " > ".join(
      part for part in (section.parent, _heading(section.number, section.title)) if part
    )
    current: list[PageLine] = []
    words = 0
    for line in section.lines:
      current.append(line)
      words += len(line.text.split())
      if words >= CHUNK_TARGET_WORDS:
        chunks.append(_chunk(section, heading_path, current))
        current, words = [], 0
    if current:
      chunks.append(_chunk(section, heading_path, current))
  return chunks


def find_definitions(chunks: Sequence[ChunkDraft]) -> list[tuple[str, int]]:
  """Return (term, chunk index) for every term a definitions section defines."""
  found: list[tuple[str, int]] = []
  seen: set[str] = set()
  for index, chunk in enumerate(chunks):
    if EvidenceAspect.DEFINITIONS not in chunk.aspects:
      continue
    for line in chunk.text.splitlines():
      match = _DEFINITION.match(line)
      if match is None:
        continue
      term = match.group("term").strip(" ,")
      key = term.casefold()
      words = key.split()
      if (
        2 <= len(term) <= 60
        and len(words) <= 6
        and words[0] not in _LEADING_FUNCTION_WORDS
        and key not in seen
      ):
        seen.add(key)
        found.append((term, index))
  return found


def tag_aspects(title: str | None, text: str) -> tuple[EvidenceAspect, ...]:
  """Tag which aspects of a claim a chunk can be evidence about."""
  heading = (title or "").casefold()
  body = text.casefold()
  aspects: list[EvidenceAspect] = []
  for aspect, (heading_pattern, body_pattern) in _ASPECT_PATTERNS.items():
    if re.search(heading_pattern, heading) or (
      body_pattern is not None and re.search(body_pattern, body)
    ):
      aspects.append(aspect)
  if EvidenceAspect.DEFINITIONS not in aspects and len(_MEANS.findall(text)) >= 3:
    aspects.append(EvidenceAspect.DEFINITIONS)
  return tuple(aspects)


def embedding_text(document_title: str, chunk: ChunkDraft) -> str:
  """Give the embedding model the document and heading context of a chunk."""
  return f"{document_title} | {chunk.heading_path}\n{chunk.text}"


# Terms may be quoted or bare, and one guide writes them in lower case ("dependant means").
_DEFINITION = re.compile(
  r"^[“\"']?(?P<term>[A-Za-z][\w’'()/,\- ]{1,58}?)[”\"']?\s+"
  r"(?:means|has the (?:same )?meaning|includes)\b"
)
_LEADING_FUNCTION_WORDS = frozenset({"a", "an", "and", "for", "in", "of", "or", "the", "to"})
_CONTENTS_TITLES = frozenset({"contents", "table of contents"})
_MEANS = re.compile(r"[”\"]\s+means\b|\bmeans\b")

_ASPECT_PATTERNS: dict[EvidenceAspect, tuple[str, str | None]] = {
  EvidenceAspect.COVERAGE: (
    r"benefit|cover|treatment|services|payment|optical|dental|medical|pharmac|ambulance",
    r"benefits? (?:are|is) (?:paid|payable)|we will (?:pay|cover|reimburse)|\d+% of",
  ),
  EvidenceAspect.EXCLUSIONS: (
    r"exclu|not covered|restricted|limitation",
    r"not payable|not covered|we will not|we do not pay|no benefits? (?:is|are|will be) payable",
  ),
  EvidenceAspect.DEFINITIONS: (r"definition|interpretation|meaning|glossary", None),
  EvidenceAspect.WAITING_PERIODS: (r"waiting", r"waiting period"),
  EvidenceAspect.LIMITS: (
    r"limit|maximum",
    r"annual limit|benefit limit|per calendar year|per financial year|up to \$",
  ),
  EvidenceAspect.CLAIMS: (
    r"claim",
    r"lodge|lodged|submit (?:a|your) claim|itemised|receipt|within \d+ (?:months|years)",
  ),
}


def _heading(number: str | None, title: str | None) -> str | None:
  parts = [part for part in (number, title) if part]
  return " ".join(parts) or None


def _chunk(section: Section, heading_path: str, lines: list[PageLine]) -> ChunkDraft:
  text_parts: list[str] = []
  page_breaks: list[tuple[int, int]] = []
  offset = 0
  previous_page: int | None = None
  for line in lines:
    if line.page != previous_page:
      page_breaks.append((offset, line.page))
      previous_page = line.page
    text_parts.append(line.text)
    offset += len(line.text) + 1
  text = "\n".join(text_parts)
  return ChunkDraft(
    section_number=section.number,
    section_title=section.title,
    heading_path=heading_path,
    scopes=section.scopes,
    page_start=lines[0].page,
    page_end=lines[-1].page,
    page_breaks=tuple(page_breaks),
    aspects=tag_aspects(heading_path, text),
    text=text,
  )


def _is_short_heading(text: str, max_words: int) -> bool:
  return (
    len(text.split()) <= max_words
    and not text.endswith((".", ",", ";"))
    and "$" not in text
  )


def _nib_sections(lines: Sequence[PageLine]) -> list[Section]:
  """nib numbers rules LS<table>.<rule>; LS1-LS3 apply to every product."""
  heading = re.compile(r"^(?P<number>LS\d+(?:\.\d+)*)\s+(?P<title>[A-Za-z].*)$")
  schedule = re.compile(r"^SCHEDULE\s+[A-Z]\b")
  applies_to = re.compile(r"apply to Schedules?\s+(?P<tables>.+)", re.IGNORECASE)
  sections: list[Section] = [Section(None, "Preamble", None, frozenset())]
  table_title: dict[str, str] = {}
  in_schedules = False
  for index, line in enumerate(lines):
    text = line.text
    match = heading.match(text)
    if schedule.match(text):
      in_schedules = True
      sections.append(Section(" ".join(text.split()[:2]).title(), text, None, frozenset()))
      continue
    if in_schedules:
      tables = applies_to.search(text)
      next_text = lines[index + 1].text if index + 1 < len(lines) else ""
      if next_text.casefold().startswith("in the table") and _is_short_heading(text, 5):
        parent = sections[-1].parent or sections[-1].title
        sections.append(Section(sections[-1].number, text, parent, frozenset()))
        continue
      if tables is not None:
        scopes = frozenset(re.findall(r"LS\d+", tables.group("tables")))
        sections[-1].scopes = scopes
      sections[-1].lines.append(line)
      continue
    if match is not None and _is_short_heading(match.group("title"), 12):
      number = match.group("number")
      table = number.split(".")[0]
      if "." not in number:
        table_title[table] = match.group("title")
      scopes = frozenset() if table in {"LS1", "LS2", "LS3"} else frozenset({table})
      parent = None if "." not in number else f"{table} {table_title.get(table, '')}".strip()
      sections.append(Section(number, match.group("title"), parent, scopes))
      continue
    sections[-1].lines.append(line)
  return sections


def _bupa_sections(lines: Sequence[PageLine]) -> list[Section]:
  """Bupa letters its general rules; Part 2 numbers one product per top-level number."""
  part = re.compile(r"^PART\s+(?P<part>\d)\b")
  # Product banners start the next product's specification; their labels are not reliable
  # (one is misnumbered), so scope still comes from the section numbers below them.
  product_banner = re.compile(r"^Product\s+\d\s*[–-]")
  lettered = re.compile(r"^(?P<number>[A-G])\.\s+(?P<title>[A-Z].*)$")
  # A bare number heading is a single digit, so a line opening "30 June 2026" is body text.
  numbered = re.compile(r"^(?P<number>(?:[A-G]|\d+)(?:\.\d+)+|[1-9])\.?\s+(?P<title>[A-Z].*)$")
  sections: list[Section] = [Section(None, "Preamble", None, frozenset())]
  current_part = 0
  parents: dict[str, str] = {}
  for line in lines:
    text = line.text
    if (found := part.match(text)) is not None:
      current_part = int(found.group("part"))
      sections.append(Section(None, text, None, frozenset()))
      continue
    if product_banner.match(text):
      sections.append(Section(None, text, None, frozenset()))
      continue
    match = lettered.match(text) or numbered.match(text)
    if match is not None and _is_short_heading(match.group("title"), 9):
      number = match.group("number")
      top = number.split(".")[0]
      if "." not in number:
        parents[f"{current_part}:{top}"] = f"{number} {match.group('title')}"
      scopes = (
        frozenset({f"P{top}"}) if current_part == 2 and top.isdigit() else frozenset()
      )
      parent = parents.get(f"{current_part}:{top}") if "." in number else None
      sections.append(Section(number, match.group("title"), parent, scopes))
      continue
    sections[-1].lines.append(line)
  return sections


def _allianz_sections(lines: Sequence[PageLine]) -> list[Section]:
  """Allianz guides use unnumbered headings: capitals, or a short line ending in a colon."""
  sections: list[Section] = [Section(None, "Introduction", None, frozenset())]
  for index, line in enumerate(lines):
    text = re.sub(r"^\d{2}\s+", "", line.text)
    letters = [character for character in text if character.isalpha()]
    upper = bool(letters) and sum(character.isupper() for character in letters) / len(
      letters
    ) > 0.8
    next_words = len(lines[index + 1].text.split()) if index + 1 < len(lines) else 0
    # PDF lines often end mid-sentence with a colon, so only a capitalised line counts.
    is_heading = text[:1].isupper() and (
      (upper and 2 <= len(text.split()) <= 12 and not any(c.isdigit() for c in text))
      or (text.endswith(":") and 2 <= len(text.split()) <= 10)
      or (
        _is_short_heading(text, 5)
        and text[:1].isupper()
        and not any(character.isdigit() for character in text)
        and not text.startswith("•")
        and next_words >= 8
      )
    )
    if is_heading:
      sections.append(Section(None, text.rstrip(":"), None, frozenset()))
      continue
    sections[-1].lines.append(line)
  return sections


_SPLITTERS: dict[DocumentLayout, Callable[[Sequence[PageLine]], list[Section]]] = {
  DocumentLayout.NIB_FUND_RULES: _nib_sections,
  DocumentLayout.BUPA_FUND_RULES: _bupa_sections,
  DocumentLayout.ALLIANZ_MEMBERS_GUIDE: _allianz_sections,
}
