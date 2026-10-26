# Sample invoices

The project uses a generated golden corpus of 12 fictional invoices plus one Dutch fuel receipt in English, Dutch, German, and French. `manifest.json` records the expected document type, normalized fields, and policy outcomes. No private document or random internet scrape belongs in this repository.

Regenerate and verify it with:

```bash
cd backend
uv run python scripts/generate_samples.py
cd ..
jq '{documents: length, pages: ([.[].pages] | add)}' samples/manifest.json
```

Evaluate the complete golden corpus against the configured live Azure resource with:

```bash
cd backend
uv run python scripts/evaluate_corpus.py
```

The extraction evaluator routes each manifest entry to `prebuilt-invoice` or `prebuilt-receipt`, compares normalized fields, and continues past individual provider failures. Running it consumes 13 Azure analyze transactions across 14 pages. `scripts/evaluate_hybrid.py` runs the Dutch invoice and fuel receipt through both extraction methods and reports primary fields, LLM fallbacks, conflicts, final status, and call counts.

The committed set contains eleven PDFs and two PNG images. VAT values are fictional checksum examples and are never presented as verified business registrations.

`assistant_questions.json` labels 12 review-history questions with the typed filter each should produce. `scripts/evaluate_assistant.py` sends only the questions, never a document, and resolves relative dates against a fixed 2026-08-15.

`claims/receipts/` holds 10 fictional health receipts for the Student claims checker: the broken-glasses story, a GP visit, a vague "Consultation", pharmacy, dental, physio, sunglasses, a blurred optical scan, a café receipt, and glasses bought in 2024. Regenerate them with `uv run python scripts/generate_claim_receipts.py`. `claims/manifest.json` labels what each receipt shows (field status and value), and for each policy check the edition, the questions asked, the sections retrieval must find, the conditions, each line's outcome, and the exact benefit. Labels come from the policy text, with the section in each check's `note`; a line the policy leaves ambiguous is left unlabelled. `scripts/evaluate_claims.py` scores the pipeline against them and needs the policies ingested first. Real receipts are only ever checked through the interface, never committed.

Microsoft's official sample invoice is downloaded locally for the first Azure provider check and ignored by Git:

```bash
curl -L \
  https://raw.githubusercontent.com/Azure-Samples/cognitive-services-REST-api-samples/master/curl/form-recognizer/sample-invoice.pdf \
  -o samples/sample-invoice.pdf
```

Optional external research datasets:

- [FATURA](https://zenodo.org/records/8261508): 10,000 synthetic English invoices across 50 layouts, CC BY 4.0.
- [DocILE](https://docile.rossum.ai/): annotated and synthetic business documents with research access.
- [CORD](https://github.com/clovaai/cord): Indonesian receipts, useful for expanding receipt evaluation.
- [SROIE](https://arxiv.org/abs/2103.10213): scanned receipt OCR benchmark.
