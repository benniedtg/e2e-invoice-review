# Pricing

Pricing checked on 2026-07-19 for the project's Document Intelligence resource and the `gpt-5.6-terra` Global Standard deployment. Azure prices are estimates: the final amount can vary by agreement, purchase date, tax, and exchange rate. Microsoft publishes current service prices through the [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices).

## Cost of this local setup

| Component | Tier | Standing cost | Usage cost in this project |
| --- | --- | ---: | ---: |
| Azure resource group | Platform container | €0 | €0 |
| Azure Document Intelligence | F0 in West Europe | €0 | First 500 analyzed pages per month are free |
| Azure OpenAI `gpt-5.6-terra` | Global Standard in Sweden Central | $0 | Two token-metered calls per upload; an optional third call only when a correction email is requested |
| Azure OpenAI `text-embedding-3-large` | Global Standard | $0 | Student claims only: policy ingest once, then one request per assessment |
| FastAPI, React, SQLite, uploaded files | Developer machine | No Azure charge | Local resources only |
| Hosting, managed database, object storage | Not deployed | €0 | €0 |

The public short-context meters used here are $2.50 per million input tokens and $15.00 per million output tokens. The recognition/review call sends the source PDF, PNG, or JPEG to Azure OpenAI. It classifies the document and can supplement fields left empty by Document Intelligence. The GL suggestion sends only normalized fields and the fixed account catalog. A correction-email request sends normalized fields plus supplier-fixable issues, not the source file.

F0 processes up to 500 pages per month. Each request is limited to the first two pages, 4 MB, and one analyze transaction per second. Azure bills Document Intelligence by pages analyzed, not by files or requests. See Microsoft's [billing and service-limit documentation](https://learn.microsoft.com/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0#billing).

## Cost of one extraction evaluation

The evaluator sends 12 invoices to `prebuilt-invoice` and one fuel receipt to `prebuilt-receipt`: 13 requests and 14 pages.

| Scenario | Price | Calculation | Full evaluation |
| --- | ---: | ---: | ---: |
| Current F0 resource | 500 pages/month free | 14 pages within allowance | **€0.00** |
| S0, USD retail | $10.00 / 1,000 prebuilt pages | 14 × $10 / 1,000 | **$0.14** |
| S0, EUR reference | €8.7758 / 1,000 prebuilt pages | 14 × €8.7758 / 1,000 | **€0.1229**, about **€0.12** |

One run uses 2.8% of the F0 allowance. In an otherwise unused month it fits 35 complete runs (490 pages), with ten pages left. Single-document checks and UI uploads consume the same allowance. F0 has no paid overage: after its quota is exhausted, use S0 or wait for the monthly reset.

## Cost of the complete hybrid evaluation

The extraction evaluator does not call Azure OpenAI. Running all 13 documents through the complete application makes two model calls per document:

1. Recognition and independent extraction: at most 8,000 input and 500 output tokens per document.
2. GL suggestion: at most 2,000 input and 100 output tokens per document.

For PDFs, the Responses API includes extracted text and page images in model context, so exact token usage varies with the document. Microsoft describes this in [PDF input for the Responses API](https://learn.microsoft.com/en-gb/azure/foundry/openai/how-to/responses?tabs=python-key#pdf-files). These are transparent planning envelopes, not fixed transaction prices.

```text
recognition/review input:  13 × 8,000 = 104,000 × $2.50 / 1M = $0.2600
recognition/review output: 13 ×   500 =   6,500 × $15.00 / 1M = $0.0975
recognition/review total                                      = $0.3575

GL input:                 13 × 2,000 = 26,000 × $2.50 / 1M = $0.0650
GL output:                13 ×   100 =  1,300 × $15.00 / 1M = $0.0195
GL total                                                       = $0.0845

complete 13-document Azure OpenAI envelope                     = $0.4420
```

The complete set is therefore about **$0.44**, plus **€0.00** for Document Intelligence while the F0 allowance remains. One ordinary hybrid document is about **$0.034** under the same two-call envelope. Dense or multi-page documents can cost more; short receipts can cost less. Responses are not cached, so deleting and reprocessing creates new usage.

## Optional correction-email cost

The correction-email model is not called during upload. It runs only when a reviewer clicks **Generate correction email**, and only for a deterministic issue the supplier can fix.

```text
input:  2,000 × $2.50 / 1M = $0.0050
output:   500 × $15.00 / 1M = $0.0075
one optional draft          = $0.0125, about 1.25 cents
```

The call returns copyable text only. It does not send an email or incur an email-provider charge.

## Optional review-history question cost

Asking the review history never sends a source file. It makes two text-only calls: one turns the question into a typed filter, and one writes the answer from at most 20 retrieved documents plus the totals SQL computed. An off-topic question, or one that matches nothing, stops after the first call.

```text
filter input:   2,000 × $2.50 / 1M = $0.0050
filter output:    300 × $15.00 / 1M = $0.0045
answer input:   4,000 × $2.50 / 1M = $0.0100
answer output:    500 × $15.00 / 1M = $0.0075
one question                        = $0.0270, about 3 cents
```

`scripts/evaluate_assistant.py` makes only the filter call, once for each of the 12 labelled questions: 12 × $0.0095, about **$0.11**.

## Student claims cost

A claim check sends the receipt to Azure OpenAI once; every later call is text only. Document Intelligence is not used. Embeddings come from the `text-embedding-3-large` Global Standard deployment on the same resource, at $0.13 per million tokens (`text-embedding-3-large-glbl Tokens`, $0.00013 per 1K, checked 2026-10-26).

The sizes below were recorded from live calls on 2026-10-26, counting characters ÷ 4 as tokens and including the strict output schema sent with each call. A receipt PDF also puts its extracted text and a page image in context; about 1,500 tokens is assumed for a one-page receipt.

| Call | When | Glasses: 3 lines, nib Premium | GP visit: 1 line, nib Core |
| --- | --- | ---: | ---: |
| Receipt reading | Once per upload | ~2,600 in / ~370 out | ~2,600 in / ~220 out |
| Embeddings | Once per assessment | ~810 | ~200 |
| Conditions reading | Once per assessment | ~24,400 in / ~770 out | ~7,800 in / ~480 out |
| Message | Each assessment and each answer | ~620 in / ~170 out | ~420 in / ~120 out |

```text
glasses receipt on nib Premium, one follow-up answer:
receipt:     2,600 × $2.50 / 1M +   370 × $15.00 / 1M = $0.0121
embeddings:    810 × $0.13 / 1M                         = $0.0001
conditions: 24,400 × $2.50 / 1M +   770 × $15.00 / 1M = $0.0726
messages:  2 × (620 × $2.50 / 1M + 170 × $15.00 / 1M)  = $0.0082
one conversation                                        = $0.0930, about 9 cents

GP receipt on nib Core, no follow-up:
receipt:     2,600 × $2.50 / 1M +   220 × $15.00 / 1M = $0.0098
conditions:  7,800 × $2.50 / 1M +   480 × $15.00 / 1M = $0.0267
message:       420 × $2.50 / 1M +   120 × $15.00 / 1M = $0.0029
one conversation                                        = $0.0394, about 4 cents
```

- The conditions reading dominates. Each line carries its own 20 to 27 retrieved passages, about 8,000 tokens a line, and a passage two lines share is sent once for each.
- The insurer and product questions make no model call.
- An answer the server decides in code (cover start date, benefits already used, referral, amount paid) re-verifies the stored conditions and costs one message, about 0.4 cents. A new service description or date changes what is searched, so it runs retrieval and the conditions reading again.
- A typed reply adds one interpretation call of about 300 input and 20 output tokens, about $0.001. Quick-reply buttons cost nothing.
- Loading the policies embeds 495 chunks once, about 83,000 tokens × $0.13 / 1M, about **$0.011** for all five editions. An unchanged file is skipped on later runs.

`scripts/evaluate_claims.py` reads 10 receipts (about $0.11), makes 11 conditions readings, four of them on the three-line glasses receipt (about $0.53), writes about 20 messages (about $0.08), and embeds its recall searches (under $0.001): about **$0.72** per run.

## Recheck the calculation

Count the committed corpus:

```bash
jq '{documents: length, pages: ([.[].pages] | add)}' samples/manifest.json
```

Expected:

```json
{
  "documents": 13,
  "pages": 14
}
```

Query the live S0 prebuilt meter for West Europe:

```bash
for currency in USD EUR; do
  curl -sG 'https://prices.azure.com/api/retail/prices' \
    --data-urlencode "currencyCode=$currency" \
    --data-urlencode "\$filter=armRegionName eq 'westeurope' and productName eq 'Azure Document Intelligence' and skuName eq 'S0' and meterName eq 'S0 Pre-built Pages'" \
    | jq '.Items[] | {currencyCode, retailPrice, unitOfMeasure, meterName}'
done
```

Query the current Global Standard short-context token meters:

```bash
curl -sG 'https://prices.azure.com/api/retail/prices' \
  --data-urlencode 'api-version=2023-01-01-preview' \
  --data-urlencode "\$filter=productName eq 'Azure OpenAI GPT5' and contains(skuName, '5.6 terra')" \
  | jq '[.Items[] | select(.armRegionName == "swedencentral") | select(.skuName == "5.6 terra ShortCo Inp Std Gl" or .skuName == "5.6 terra ShortCo Opt Std Gl") | {skuName, retailPrice, currencyCode, unitOfMeasure}] | unique_by(.skuName)'
```

Use Azure Cost Management for the subscription's actual billed amount. The Retail Prices API does not include negotiated discounts or taxes.
