# LedgerFlow — Project Context for Claude

## What this project is

LedgerFlow is a financial transaction management system for small businesses. It ingests bank statements (CSV) and vendor invoices (PDF), auto-categorizes transactions using regex rules, and surfaces uncategorized items in a review queue.

Stack: FastAPI + PostgreSQL backend, React + TypeScript + Tailwind frontend, AWS Bedrock for chat, vLLM (h2oai/h2ovl-mississippi-800m) for PDF OCR.

---

## How to run

```powershell
# Backend
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173`. CORS is hardcoded to that origin in `app/main.py`.

---

## Architecture

```
frontend/          React + TypeScript + Tailwind (Vite)
app/
  api/routes/      FastAPI routers (businesses, documents, transactions, accounts, health)
  models/          SQLAlchemy ORM models
  schemas/         Pydantic schemas (request/response)
  services/        Business logic (CSV, OCR, categorization, seeding)
  db/              SQLAlchemy engine + SessionLocal + Base
  core/config.py   Settings from .env via pydantic-settings
alembic/           DB migrations
scripts/           OCR test scripts (not part of the app)
```

---

## Database models (key tables)

| Table | Purpose |
|---|---|
| `businesses` | Top-level tenant. Everything scoped to business_id |
| `documents` | Uploaded files (CSV/PDF). Has invoice_number, invoice_date, due_date for PDFs |
| `document_extractions` | Raw OCR JSON output + model name (audit trail) |
| `transactions` | One row per line item. Core entity |
| `categories` | Chart of accounts. Self-referential tree |
| `vendors` | Upserted from invoice vendor_name. FK on transactions |
| `categorization_rules` | Regex patterns → category + transaction_type + confidence |
| `duplicate_groups` / `duplicate_group_members` | Fingerprint-based dedup |
| `review_items` | Flagged issues awaiting human review |
| `users` | Multi-tenant skeleton — not yet wired to auth |

### Transaction fields that matter most
- `description_raw` — raw text (from CSV column or invoice line item description)
- `merchant_name` — vendor name (from OCR)
- `vendor_id` — FK to vendors table (upserted from OCR)
- `amount` — Decimal(14,2), always positive
- `direction` — INFLOW / OUTFLOW
- `transaction_type` — revenue, expense, transfer, owner_draw, etc.
- `review_status` — needs_review → auto_approved / user_approved / user_corrected / ignored
- `fingerprint_hash` — SHA256(business_id:date:description:amount) for dedup

### Document fields added in latest migration (383ea72fbdc5)
- `invoice_number`, `invoice_date`, `due_date` — populated after PDF OCR

---

## CSV pipeline (fully working)

1. Upload `.csv` with columns: `date`, `description`, `amount` (case-insensitive, optional `notes`)
2. `csv_parser.parse_csv()` runs synchronously in the route — fingerprints + dedup
3. Positive amount → INFLOW, negative → OUTFLOW
4. Transactions created with `review_status = NEEDS_REVIEW`
5. Background task: `categorize_transactions(business_id, document_id)` runs regex rules
6. Rules loaded from `categorization_rules` table (seeded via `/businesses/{id}/setup`)
7. Confidence >= 0.75 → `AUTO_APPROVED`, below → stays `NEEDS_REVIEW`

---

## PDF OCR pipeline (in progress — THIS IS THE ACTIVE WORK)

### OCR model
- Model: `h2oai/h2ovl-mississippi-800m` (800M params, literal, low reasoning)
- Hosted on vLLM (EC2 or RunPod), OpenAI-compatible API
- Config: `settings.vllm_base_url`, `settings.vllm_api_key`, `settings.ocr_model`

### What we extract from invoices
```json
{
  "vendor_name": "...",
  "invoice_number": "...",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "line_items": [
    {"description": "...", "quantity": 1, "net_price": 100.00}
  ]
}
```
- `amount` per line item = `quantity * net_price` (calculated in post-processing, not by model)
- `total_amount` excluded — not stored in DB, derivable by summing line items

### How invoice data maps to DB
- `Document`: invoice_number, invoice_date, due_date, source_type=vendor_bill
- `DocumentExtraction`: full raw JSON + model_used (audit trail)
- `Vendor`: upsert by normalized_name (vendor_name.strip().lower())
- `Transaction` (one per line item):
  - `description_raw` = line item description
  - `amount` = quantity * net_price
  - `merchant_name` = vendor_name
  - `vendor_id` = FK to Vendor
  - `transaction_date` = invoice_date
  - `direction` = OUTFLOW
  - `transaction_type` = EXPENSE
  - `review_status` = NEEDS_REVIEW

### Prompt approach (from scripts/test.py — single pass, template-based)
The Mississippi model works best with an explicit JSON template with nulls. It fills in the blanks rather than reasoning about structure.

```
Extract invoice data from the image.
Return JSON only. Do not explain. Do not add extra keys. Do not guess.
Use null if a value is not visible.

Extract:
* vendor_name
* invoice_number
* invoice_date in YYYY-MM-DD format
* due_date in YYYY-MM-DD format

For each line item, extract only:
* description: item name
* quantity: quantity of the item
* net_price: price per single unit before tax

Return exactly this format:
{"vendor_name": null, "invoice_number": null, ...}
```

### What needs to be implemented (current TODO)

`app/api/routes/documents.py` line 20 has this already planned:
```python
# from app.services.ocr_service import process_pdf_document
```

**`ocr_service.py` changes needed:**
1. Replace old schema-driven `ocr_extract(file_path, schema)` with `extract_invoice(file_path) -> InvoiceExtraction`
2. Add `process_pdf_document(document_id, business_id)` standalone background task at bottom
   - Same pattern as `categorize_transactions` in `categorization_service.py`
   - Creates own `SessionLocal()`, calls `extract_invoice`, writes DB records, calls `categorize_transactions`

**`documents.py` fixes:**
1. Remove `from app.services.ocr_service import OCRService` (line 17)
2. Uncomment `from app.services.ocr_service import process_pdf_document` (line 20)
3. Fix line 136: `background_tasks.add_task(process_pdf_document, doc.id, business_id)`

---

## Services reference

| Service | File | Key method |
|---|---|---|
| DocumentService | `services/document_service.py` | `read_and_checksum`, `save_to_disk`, `create_document` |
| CSVParser | `services/csv_parser.py` | `parse_csv(file_content, business_id, document_id, existing_fingerprints)` |
| CategorizationService | `services/categorization_service.py` | `categorize_transactions(business_id, document_id)` |
| OCRService | `services/ocr_service.py` | `extract_invoice(file_path)` ← being rebuilt |
| SeeedingService | `services/seeding_service.py` | `seed_business_defaults(db, business_id)` |
| BedrockService | `services/bedrock_service.py` | `invoke(message, prompt)` — Claude Haiku via Bedrock |

---

## Seeded categorization rules (after /setup)

| Pattern | Category | Confidence |
|---|---|---|
| stripe, paypal, square, shopify | Revenue | 0.80 |
| aws, google cloud, azure, vercel, cloudflare | Software & SaaS | 0.85 |
| github, notion, figma, slack, zoom, loom, canva | Software & SaaS | 0.85 |
| gusto, rippling, adp, deel | Payroll & Contractors | 0.85 |
| google ads, facebook ads, meta ads, linkedin ads | Marketing & Advertising | 0.85 |
| uber, lyft, airbnb, delta air, expedia | Travel & Transport | 0.75 |
| doordash, starbucks, chipotle, restaurant, cafe | Meals & Entertainment | 0.70 |
| bank fee, service fee, overdraft fee, wire fee | Bank Fees | 0.85 |
| amazon, staples, fedex, ups, usps | Office & Operations | 0.65 |
| transfer, zelle, wire transfer, venmo | Transfer | 0.70 |
| owner draw, owner withdrawal | Owner Draw | 0.85 |

Confidence threshold: **0.75** — anything below stays NEEDS_REVIEW.

---

## Known gaps (not MVP blockers)

- No auth / session middleware (User model exists, not wired)
- No API routes for: DuplicateGroups, ReviewItems, CategorizationRules management
- `DocumentOut` schema missing `invoice_number`, `invoice_date`, `due_date` fields
- Frontend `Transaction` type missing `customer_id`, `vendor_id`
- Large transaction review item creation not implemented

---

## Test data

Sample CSV at `scripts/sample_bank_statement.csv` — 28 transactions covering all seeded rule categories, mixes of auto-approved and needs_review, includes one duplicate row.

OCR test scripts at `scripts/test.py` (single-pass, working) and `scripts/test_ocr_pdf.py` (2-pass experimental).
