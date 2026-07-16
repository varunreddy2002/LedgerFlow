# LedgerFlow — Project Context for Claude

## What this project is

LedgerFlow is a financial transaction management system for small businesses. It ingests bank statements (CSV) and vendor invoices/bills (PDF), classifies and categorizes transactions (regex rules + LLM fallback), and exposes a chat agent that can query the data, compute P&L, and generate charts.

Stack: FastAPI + PostgreSQL backend, React + TypeScript + Tailwind frontend, LangGraph for all agent/workflow orchestration, AWS Bedrock (Claude) for chat, structured extraction, and PDF OCR.

Architecture style: pragmatic clean architecture (see below) — not textbook-strict. ORM models import `Base` from infrastructure directly, and simple read-only routes query the DB inline rather than going through a service layer. Both are intentional trade-offs for a codebase this size, not oversights.

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
frontend/                  React + TypeScript + Tailwind (Vite)
app/
  interface/api/routes/    FastAPI routers (businesses, accounts, documents, transactions, chat, health)
  domain/
    models/                SQLAlchemy ORM models (business, transaction, document, chat, user, audit)
    schemas/                Pydantic schemas (request/response + LLM structured-output schemas)
    enums.py                All StrEnum types shared across the app
  application/
    agents/                 LangGraph agents/workflows (chat, categorization, pnl, document_agent, sandbox)
    services/                Orchestration services (ingestion, transaction summary, seeding)
  infrastructure/
    db/                      SQLAlchemy engine + SessionLocal + Base + session_scope()
    llm/                     BedrockService (chat/structured output) + ocr_client (PDF extraction)
    storage/                 Document storage helpers
  core/
    config.py                Settings from .env via pydantic-settings
    logging.py                Logger setup
alembic/                    DB migrations
scripts/                    OCR/test scripts, sample CSV, fake PDF generator (not part of the app)
```

**Layer dependency rule:** `interface` → `application` → `domain`, with `infrastructure` reachable from any layer (DB session, LLM clients). Routes stay thin — they call `application/services` or `application/agents` and translate to/from `domain/schemas`. Business logic that needs judgment (LLM calls, multi-step decisions) lives under `agents/`; deterministic logic (aggregation, CRUD) lives under `services/`.

---

## Database models (key tables)

| Table | Purpose |
|---|---|
| `businesses` | Top-level tenant. Everything scoped to business_id |
| `accounts` | Bank/credit-card accounts (checking, savings, credit_card, cash, other) |
| `documents` | Uploaded files (CSV/PDF). `source` = bank_statement / credit_card / vendor_bill / invoice |
| `document_extractions` | Raw LLM extraction JSON + model name (audit trail) |
| `transactions` | One row per line item on a bank statement, or one per invoice/bill header. Core entity |
| `transaction_line_items` | Line items under a PDF-sourced transaction (invoice/bill detail) |
| `categories` | Chart-of-accounts-lite. Self-referential tree. `category_type`: revenue / expense / transfer / owner_draw |
| `vendors` / `customers` | Upserted by normalized name during ingestion or categorization party-matching |
| `categorization_rules` | Regex patterns → category + confidence, ordered by priority |
| `chat_sessions` / `chat_messages` | Chat agent conversation persistence (paired with LangGraph's own Postgres checkpointer) |
| `users` | Multi-tenant skeleton — not yet wired to auth |
| `audit_logs` | Generic audit trail table — not yet written to by any code path |

**Not yet modeled:** no `duplicate_groups`/`review_items` tables exist despite dedup/large-transaction settings in config (`categorization_confidence_threshold`, `large_transaction_threshold`) — those thresholds are currently only half-wired (see Known gaps). No double-entry ledger (`journal_entries`/`journal_entry_lines`) — P&L is computed directly off `transactions`, cash-basis only.

### Transaction fields that matter most
- `description` — raw text (CSV column or invoice line item / seller name)
- `date`, `due_date`
- `amount` — `NUMERIC(14,2)`, always positive
- `trans_type` — one of:
  - `debit` — money OUT of bank (bank statement / credit card)
  - `credit` — money IN to bank (bank statement / credit card)
  - `payable` — we owe (from a vendor bill PDF, no cash movement yet)
  - `receivable` — owed to us (from an invoice PDF, no cash movement yet)
- `category_id`, `vendor_id`, `customer_id` — nullable FKs, set by ingestion/categorization
- `review_status` — `uncategorized → needs_review → auto_approved / user_approved / user_corrected / ignored`
- `fingerprint_hash` — reserved for dedup, **currently not populated** (see ingestion notes)
- **No `business_id` column** — always scope transactions by joining `documents` on `document_id`

### Migrations
Two migrations exist: `36c7032ff4b8_initial_schema` and `a0ab2b840a85_add_payable_receivable_to_transaction_`. Schema is managed entirely by Alembic — `app/main.py` does not call `create_all()`.

---

## Agents vs. workflows — know the difference in this codebase

Everything under `app/application/agents/` is built as a LangGraph graph, but only one of them is actually agentic (dynamic tool selection + reasoning loop). The rest are fixed-shape workflows with an LLM step embedded — that's a deliberate, correct choice for parts where you want deterministic, auditable behavior (e.g. P&L math), but don't mistake the graph wrapper for agentic behavior when reasoning about how to extend these.

| Agent | Real agent? | Behavior |
|---|---|---|
| `chat/` | **Yes** | LangGraph loop (`agent` ⇄ `run_tools`), dynamic tool calls (`query_database`, `get_pnl`, `request_chart`), `interrupt()`-based human-in-the-loop for chart confirmation, Postgres checkpointer (survives restarts), sandboxed matplotlib execution via Docker (`sandbox_service.py`) with one retry on failure. |
| `categorization/` | No — rules engine + LLM fallback | Fixed DAG: `load_data → match_party → apply_rules → (conditional) → llm_categorize → persist`. Regex rules run first (priority order, first match wins); only *unmatched* transactions go to a single structured-output LLM call. No tool use, no retry, no escalation path. |
| `pnl/` | No — and shouldn't be | Fixed DAG, **zero LLM calls**: `gate → load → compute → format`. Gate blocks the whole report if any bank/credit-card transaction in the period is uncategorized. Called by the chat agent as a tool (`get_pnl`) rather than reasoned about inline — correct pattern, keep it deterministic. |
| `document_agent.py` | No — two standalone LLM calls | `map_columns` (CSV header → canonical field mapping, only invoked when headers don't already match) and `extract_document` (PDF → structured `ExtractedDocument` via Bedrock, `ocr_client.with_structured_output`). No loop, no retry. |

**Chat system prompt cost note:** `chat/nodes.py` binds all 3 tools plus a ~100-line hardcoded `SCHEMA` string into the system prompt on every single turn, regardless of whether the question needs the schema. If adding more tools (accounting/reconciliation skills), prefer a deferred-loading pattern (lightweight tool index always in context, full schema/instructions fetched on demand) over growing this static prompt further.

---

## Ingestion pipeline (`application/services/ingestion_service.py`)

Entry point: `run_ingestion(business_id, filename, content, ext)` — called as a FastAPI `BackgroundTask` from `POST /businesses/{id}/documents/upload`. Synchronous, single-threaded per call, one `session_scope()` for the whole document.

**CSV path** (`_process_csv`):
1. If headers exactly match `{date, description, amount, trans_type}` (case-insensitive), map directly.
2. Otherwise call the `map_columns` agent to infer the mapping from headers + a 3-row sample.
3. If any required field maps to `None`, the document is marked `FAILED` and processing stops — no retry, no partial import.
4. Row `amount` sign determines `trans_type` (negative → debit, positive → credit); stored amount is always positive.
5. Fingerprinting is **not implemented** — the `fingerprint_hash` column exists but is never set from this path, so no dedup happens on CSV import.

**PDF path** (`_process_pdf`):
1. `extract_document` pulls structured invoice/bill data from the PDF via Bedrock.
2. Classification (`_classify`) compares the business's own name against `seller_name`/`buyer_name` (normalized string equality) to decide invoice vs. vendor_bill and who the counterparty is. **If neither matches exactly (typos, DBAs, subsidiaries), classification fails and the document is marked `FAILED`** — this is the most fragile part of the pipeline; no fuzzy matching or human escalation exists yet.
3. Vendor/customer is upserted by normalized-name substring match (`_upsert_party`).
4. One `Transaction` is created per document (header-level; `payable` or `receivable`), plus one `TransactionLineItem` per invoice line item.
5. Raw extraction JSON is stored in `document_extractions` for audit.

**After either path succeeds:** `run_categorization(business_id)` runs synchronously in the same background task, across *all* uncategorized transactions for the business (not just the ones from this document).

---

## Seeded categorization rules (after `/businesses/{id}/setup`)

Seed data lives in `application/services/seeding_service.py`, tuned for a consulting/professional-services business. Calling `/setup` is idempotent — it skips categories/rules that already exist by name/pattern.

| Pattern (excerpt) | Category | Confidence |
|---|---|---|
| stripe, paypal, wise, bill.com, invoice payment | Consulting Revenue | 0.75 |
| upwork, fiverr, toptal, gun.io | Subcontractors & Freelancers | 0.80 |
| gusto, rippling, adp, justworks, deel | Payroll & Benefits | 0.85 |
| aws, google cloud, github, notion, figma, slack, anthropic, vercel | Software & SaaS | 0.85 |
| legal, attorney, quickbooks, cpa, insurance | Professional Services | 0.80 |
| google ads, linkedin ads, hubspot, mailchimp | Marketing & Business Development | 0.80 |
| delta, united, airbnb, marriott, uber, lyft | Travel & Client Meetings | 0.75 |
| starbucks, doordash, grubhub, chipotle | Meals & Entertainment | 0.70 |
| udemy, coursera, conference, summit | Training & Development | 0.75 |
| amazon, staples, fedex, wework | Office & Admin | 0.65 |
| bank fee, wire fee, stripe fee | Bank & Payment Fees | 0.85 |
| irs, franchise tax, estimated tax | Taxes & Government | 0.85 |
| owner draw, distribution, partner draw | Owner Draw | 0.85 |
| transfer, zelle, venmo, ach transfer | Transfer | 0.70 |

Confidence threshold: **`settings.categorization_confidence_threshold` = 0.75** — below it, transactions stay `NEEDS_REVIEW` even after a rule matches.

---

## Services reference

| Service | File | Key method |
|---|---|---|
| `run_ingestion` | `application/services/ingestion_service.py` | Entry point for both CSV and PDF upload processing |
| `TransactionService` | `application/services/transaction_service.py` | `get_summary(db, business_id, start_date?, end_date?)` — inflow/outflow/review-status aggregates |
| `seed_business_defaults` | `application/services/seeding_service.py` | Idempotent category + rule seeding for a new business |
| `run_categorization` | `application/agents/categorization/graph.py` | Categorizes all `UNCATEGORIZED` transactions for a business |
| `run_pnl` | `application/agents/pnl/graph.py` | Cash-basis P&L for a date range; fails closed if anything in range is uncategorized |
| `map_columns` / `extract_document` | `application/agents/document_agent.py` | CSV header mapping / PDF structured extraction, both via Bedrock |
| `run_chat` / `resume_chat` | `application/agents/chat/chat.py` | Entry points into the chat LangGraph, wrapped by `chat/service.py` for session persistence |
| `BedrockService` | `infrastructure/llm/bedrock_client.py` | `invoke(message, prompt)`, `invoke_structured(message, prompt, schema)` — generic Bedrock wrapper |

---

## Config notes (`app/core/config.py`)

- `default_chat_model` / `default_sonnet_model` are both Claude Sonnet on Bedrock — chat and PDF OCR use the same model family, routed through `BedrockService`/`ocr_client` respectively.
- `ocr_provider`, `vllm_base_url`, `vllm_api_key`, `ocr_model` (h2ovl-mississippi) are **dead config** — no code path reads them. OCR actually goes through `infrastructure/llm/bedrock_client.py`'s `ocr_client` (Bedrock Sonnet), not vLLM. Remove or wire up before trusting these settings.
- `large_transaction_threshold` and `rule_cache_ttl_seconds` are declared but **not read anywhere in `app/`** — no large-transaction flagging exists, and there is no rule cache (rules are re-queried from the DB on every categorization run).

---

## Known gaps (not MVP blockers, but relevant to any agentic/accounting work)

- No auth / session middleware (`User` model exists, not wired to any route).
- No API routes for `CategorizationRules` management, or for reviewing/approving flagged items — corrections happen only via `PATCH /transactions/{id}`.
- No dedup: `fingerprint_hash` column exists on `Transaction` but nothing populates or checks it.
- No AP/AR settlement: a `payable`/`receivable` transaction from a bill/invoice is never linked to the bank transaction that eventually pays it. Accrual reporting and AP/AR aging are not possible with the current schema.
- No double-entry ledger: `categories` mixes chart-of-accounts structure with P&L bucketing and only supports revenue/expense/transfer/owner_draw — a balance sheet is not structurally representable today.
- Ingestion failure modes are dead ends: bad CSV mapping or unmatched PDF party classification both just set `status = FAILED` with a log line — no retry, fuzzy match, or human-review escalation.
- `audit_logs` table exists but nothing writes to it.

---

## Test data / scripts

- `scripts/sample_bank_statement.csv` — sample CSV for exercising the ingestion + categorization pipeline.
- `scripts/make_fake_pdfs.py` — generates synthetic invoice/bill PDFs for testing the OCR pipeline.
- `scripts/seed_accounts.py`, `scripts/smoke_test.py` — setup/smoke helpers.
- `scripts/test.py`, `scripts/test_ocr.py`, `scripts/test_ocr_pdf.py`, `scripts/test_docling.py`, `scripts/test-claude.py` — standalone OCR/LLM experiments, not part of the app.
