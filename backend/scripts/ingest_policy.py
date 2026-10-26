from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

if __package__ in {None, ""}:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.claims import repository  # noqa: E402
from app.claims.catalog import POLICY_DIRECTORY, POLICY_DOCUMENTS  # noqa: E402
from app.claims.knowledge import (  # noqa: E402
  chunk_sections,
  embedding_text,
  find_definitions,
  read_pdf_lines,
  split_sections,
)
from app.config import load_azure_openai_settings  # noqa: E402
from app.documents.database import SessionFactory, initialize_database  # noqa: E402
from app.providers import AzureOpenAIProvider  # noqa: E402

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


def main() -> int:
  parser = argparse.ArgumentParser(
    description=(
      "Chunk, embed, and store the catalog's OSHC policy PDFs from data/policies/. "
      "Embedding makes billable Azure OpenAI calls (well under a cent per document)."
    ),
  )
  parser.add_argument("documents", nargs="*", help="Catalog document IDs; default is all")
  parser.add_argument("--download", action="store_true", help="Fetch missing files first")
  parser.add_argument("--force", action="store_true", help="Re-ingest unchanged files")
  arguments = parser.parse_args()

  catalog = {document.id: document for document in POLICY_DOCUMENTS}
  unknown = set(arguments.documents) - catalog.keys()
  if unknown:
    parser.error(f"Unknown document ID(s): {', '.join(sorted(unknown))}")
  selected = [catalog[key] for key in arguments.documents] or list(POLICY_DOCUMENTS)

  initialize_database()
  provider = AzureOpenAIProvider(load_azure_openai_settings())
  failures = 0
  with SessionFactory() as session:
    ingested = repository.ingested_documents(session)
    for document in selected:
      path = POLICY_DIRECTORY / document.file_name
      if not path.is_file() and arguments.download:
        _download(document.source_url, path)
      if not path.is_file():
        failures += 1
        print(f"MISSING  {document.id}: save {document.source_url}\n         to {path}")
        continue

      digest = hashlib.sha256(path.read_bytes()).hexdigest()
      existing = ingested.get(document.id)
      if existing is not None and existing.sha256 == digest and not arguments.force:
        print(f"SKIP     {document.id}: unchanged ({existing.chunk_count} chunks)")
        continue

      lines = read_pdf_lines(path)
      chunks = chunk_sections(split_sections(lines, document.layout))
      definitions = find_definitions(chunks)
      vectors = provider.embed([embedding_text(document.title, chunk) for chunk in chunks])
      repository.replace_document(
        session,
        document_id=document.id,
        sha256=digest,
        page_count=max(line.page for line in lines),
        chunks=chunks,
        vectors=vectors,
        definitions=definitions,
      )
      print(
        f"INGESTED {document.id}: {len(chunks)} chunks, {len(definitions)} definitions"
      )
  return 1 if failures else 0


def _download(url: str, path: Path) -> None:
  """Fetch one public PDF; some insurers block scripts, so failures are reported."""
  request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
  try:
    with urllib.request.urlopen(request, timeout=60) as response:
      body = response.read(MAX_DOWNLOAD_BYTES + 1)
  except OSError as error:
    print(f"DOWNLOAD FAILED {url}: {error}")
    return
  if len(body) > MAX_DOWNLOAD_BYTES or not body.startswith(b"%PDF-"):
    print(f"DOWNLOAD REJECTED {url}: not a PDF under 10 MB (likely a bot check)")
    return
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(body)


if __name__ == "__main__":
  raise SystemExit(main())
