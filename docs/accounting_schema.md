# LedgerFlow — Double-Entry Accounting Schema (proposed)

Status: **DRAFT — for approval.** No migrations written yet.

Conventions (match existing codebase):
- Every table has `id` (BIGINT PK) via `PrimaryKeyMixin`.
- `created_at` / `updated_at` via `TimestampMixin`; audit-only tables use `CreatedAtMixin` (`created_at` only).
- Enums stored as `VARCHAR + CHECK` via `enum_column` (portable, human-readable).
- Money = `Numeric(14, 2)`. Quantities = `Numeric(14, 4)`.
- One business = **one ledger, one journal** → no `ledgers` / `journals` tables. Journal context is the `journal_type` enum on `transactions`.

Legend for the tables below: **PK** primary key · **FK** foreign key · columns from `PrimaryKeyMixin`/`TimestampMixin` are omitted (assume `id`, `created_at`, `updated_at`).

---

## 0. Enums (new / changed)

```python
class AccountType(StrEnum):        # replaces the 4-value CategoryType
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

class NormalBalance(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"

class JournalType(StrEnum):        # start with GENERAL only
    GENERAL = "general"
    SALES = "sales"
    PURCHASE = "purchase"
    BANK = "bank"
    ADJUSTMENT = "adjustment"

class TxnEventType(StrEnum):       # what real-world event the JE represents
    BILL = "bill"
    INVOICE = "invoice"
    PAYMENT = "payment"
    ADJUSTMENT = "adjustment"
    OPENING_BALANCE = "opening_balance"
    MANUAL = "manual"

class TxnStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    POSTED = "posted"
    REVERSED = "reversed"

class BillStatus(StrEnum):
    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"

class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"

class BankTxnStatus(StrEnum):
    UNPROCESSED = "unprocessed"
    PROPOSED = "proposed"
    POSTED = "posted"
    EXCLUDED = "excluded"

# NOTE: no INFLOW/OUTFLOW anywhere. Cash movement is expressed in proper
# double-entry terms via NormalBalance (debit / credit). A deposit into a
# cash (asset) account is a DEBIT to that account; a withdrawal is a CREDIT.

class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"

class AgentRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class MatchStatus(StrEnum):
    PROPOSED = "proposed"
    MATCHED = "matched"
    REJECTED = "rejected"
```

---

## A. Ledger core — the 3 tables that ARE accounting

### `accounts` — chart of accounts *(evolves from `categories`)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `account_code` | String(10) | no | e.g. `1110`, `5320` |
| `account_name` | String(120) | no | was `categories.name` |
| `account_type` | enum AccountType | no | asset/liability/equity/revenue/expense |
| `account_subtype` | String(50) | yes | CASH, RECEIVABLE, PREPAID… optional grouping |
| `parent_account_id` | FK accounts (self) | yes | hierarchy — was `parent_category_id` |
| `hierarchy_level` | SmallInt | no | 1/2/3, default 3 |
| `normal_balance` | enum NormalBalance | no | asset+expense=debit; else credit |
| `posting_allowed` | bool | no | only level-3 leaves = true |
| `is_control_account` | bool | no | AR / AP flag, default false — see note |
| `is_active` | bool | no | default true |

Unique: `(business_id, account_code)`.

**`is_control_account`** = this GL account is the *summary* of a subsidiary ledger. The two classic ones are **Accounts Receivable** (`1210`) and **Accounts Payable** (`2110`): the account's balance in the GL must equal the sum of all open `invoices` / `bills` (the subledger detail). The flag lets the system (a) reconcile the control balance against the subledger, and (b) block ad-hoc manual postings to it. A control account is still a level-3 posting leaf — you post the AP/AR side of a bill/invoice JE to it; the per-vendor/per-customer breakdown lives in `bills`/`invoices`.

**3-level hierarchy rule:** level 1 = account type (`1000 Assets`, `posting_allowed=false`), level 2 = reporting category (`1100 Cash`, `posting_allowed=false`), level 3 = posting leaf (`1110 Operating Checking`, `posting_allowed=true`). **`entries` may only reference `posting_allowed=true` accounts.** Reports roll level-3 balances up into level-2 and level-1 totals via `parent_account_id`.

### `transactions` — journal-entry header *(reshaped from current flat table)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | **added** (old table scoped via document) |
| `journal_type` | enum JournalType | no | default GENERAL |
| `transaction_number` | String(30) | yes | human JE number, generated on post |
| `transaction_date` | Date | no | economic event date |
| `effective_date` | Date | yes | accounting/period date, defaults to txn date |
| `description` | String(512) | yes | |
| `event_type` | enum TxnEventType | no | bill/invoice/payment/adjustment/manual |
| `status` | enum TxnStatus | no | default DRAFT — **this is also the "proposal" state** |
| `posted_at` | DateTime | yes | |
| `confidence_score` | Float | yes | set when the agent drafted this JE (null = human/manual) |
| `agent_run_id` | FK agent_runs | yes | which agent run drafted it, if any |
| `source_document_id` | FK documents | yes | traceability back to the upload |
| `reverses_transaction_id` | FK transactions (self) | yes | for reversal entries |

**Removed vs. today:** `amount`, `category_id`, `trans_type`, `vendor_id`, `customer_id`, `due_date`, `fingerprint_hash`, `review_status` — these move to `entries` / `bills` / `invoices` / `bank_transactions`.

**Proposal = a DRAFT transaction (decision #1, simplified).** The agent writes a `transactions` row with `status=PENDING_APPROVAL` and its `entries`; approval flips it to `POSTED`. No separate proposal tables, no copy step. A transaction only counts in reports when `status=POSTED`.

### `entries` — debit/credit lines *(new — the heart)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `transaction_id` | FK transactions | no | |
| `account_id` | FK accounts | no | must have `posting_allowed=true` |
| `sequence_number` | SmallInt | no | line order |
| `description` | String(512) | yes | |
| `debit_amount` | Numeric(14,2) | no | default 0 |
| `credit_amount` | Numeric(14,2) | no | default 0 |
| `currency` | String(3) | no | default business currency |
| `reason_code` | String(60) | yes | why the agent chose this account (audit) |
| `confidence_score` | Float | yes | line-level agent confidence, null if manual |

Uses `CreatedAtMixin` only (lines are immutable once posted).

**Invariants (DB CHECK + app-level):**
- `debit_amount >= 0 AND credit_amount >= 0`
- `NOT (debit_amount > 0 AND credit_amount > 0)` — one side only
- `debit_amount > 0 OR credit_amount > 0` — no empty lines
- per POSTED transaction: `SUM(debit_amount) = SUM(credit_amount)` (enforced in service, not DB)

---

## B. Sources — feed the ledger

### `bills` — vendor bills (AP) *(replaces `payable` transactions)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `vendor_id` | FK vendors | no | |
| `source_document_id` | FK documents | yes | |
| `transaction_id` | FK transactions | yes | the posted JE, once approved |
| `bill_number` | String(60) | yes | vendor's number |
| `bill_date` | Date | no | |
| `due_date` | Date | yes | |
| `currency` | String(3) | no | |
| `subtotal_amount` | Numeric(14,2) | no | |
| `tax_amount` | Numeric(14,2) | no | default 0 |
| `total_amount` | Numeric(14,2) | no | |
| `outstanding_amount` | Numeric(14,2) | no | starts = total, decremented by payments |
| `status` | enum BillStatus | no | default UNPAID |

Unique: `(business_id, vendor_id, bill_number)`.

### `bill_lines` *(from `transaction_line_items`)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `bill_id` | FK bills | no | |
| `line_number` | SmallInt | no | |
| `description` | String(512) | yes | |
| `quantity` | Numeric(14,4) | yes | |
| `unit_price` | Numeric(14,2) | yes | |
| `line_amount` | Numeric(14,2) | no | |
| `tax_amount` | Numeric(14,2) | yes | |
| `account_id` | FK accounts | yes | proposed/approved expense account |

### `invoices` — customer invoices (AR) *(replaces `receivable` transactions)*

Same shape as `bills` but party = customer:

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `customer_id` | FK customers | no | |
| `source_document_id` | FK documents | yes | |
| `transaction_id` | FK transactions | yes | posted JE |
| `invoice_number` | String(60) | yes | |
| `invoice_date` | Date | no | |
| `due_date` | Date | yes | |
| `currency` | String(3) | no | |
| `subtotal_amount` | Numeric(14,2) | no | |
| `tax_amount` | Numeric(14,2) | no | default 0 |
| `total_amount` | Numeric(14,2) | no | |
| `outstanding_amount` | Numeric(14,2) | no | |
| `status` | enum InvoiceStatus | no | default UNPAID |

Unique: `(business_id, invoice_number)`.

### `invoice_lines` *(from `transaction_line_items`)*
Same columns as `bill_lines`, with `invoice_id` FK instead of `bill_id`; `account_id` = revenue account.

### `bank_transactions` — raw imported bank rows *(replaces bank `debit`/`credit` transactions)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `gl_account_id` | FK accounts | no | the ASSET account this statement belongs to (e.g. 1110) |
| `source_document_id` | FK documents | yes | the CSV upload |
| `transaction_id` | FK transactions | yes | posted JE once categorized |
| `external_transaction_id` | String(120) | yes | bank's id if present |
| `transaction_date` | Date | no | |
| `posted_date` | Date | yes | |
| `description` | String(1024) | yes | raw bank text |
| `normalized_description` | String(1024) | yes | cleaned |
| `amount` | Numeric(14,2) | no | always positive |
| `cash_movement` | enum NormalBalance | no | **debit** = cash account increased (deposit) · **credit** = decreased (withdrawal) |
| `currency` | String(3) | no | |
| `fingerprint_hash` | String(64) | yes | **now actually used** for dedup |
| `status` | enum BankTxnStatus | no | default UNPROCESSED |

Unique: `(gl_account_id, external_transaction_id)` when present, else fingerprint.

### `payment_allocations` — settle AP/AR *(new — the missing link)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `bank_transaction_id` | FK bank_transactions | no | the cash movement that pays |
| `bill_id` | FK bills | yes | exactly one of bill/invoice set |
| `invoice_id` | FK invoices | yes | |
| `allocated_amount` | Numeric(14,2) | no | supports partial payment |

CHECK: exactly one of `bill_id`, `invoice_id` is non-null.

> **Deferred:** a separate `payments` table. For now a payment IS a `bank_transaction`, and allocations point straight at it. Add `payments` only when one payment spans multiple bank rows or is non-bank cash.

---

## C. Agent layer — propose → approve → post

### `agent_runs`

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `source_document_id` | FK documents | yes | |
| `bill_id` / `invoice_id` / `bank_transaction_id` | FK | yes | what was processed |
| `workflow_name` | String(80) | no | LangGraph graph name |
| `workflow_version` | String(20) | yes | |
| `model_name` | String(120) | yes | |
| `prompt_version` | String(20) | yes | |
| `status` | enum AgentRunStatus | no | |
| `input_payload` | JSONB | yes | |
| `output_payload` | JSONB | yes | |
| `error_details` | Text | yes | |
| `started_at` | DateTime | no | |
| `completed_at` | DateTime | yes | |

> **No `accounting_proposals` / `proposal_lines` tables (decision #1).** A proposal is just a `transactions` row with `status=PENDING_APPROVAL` plus its `entries` (which carry `reason_code` + `confidence_score`). This avoids a duplicate table pair and a copy-on-approve step.

### `approval_events`

| Column | Type | Null | Notes |
|---|---|---|---|
| `transaction_id` | FK transactions | no | the draft JE being decided |
| `decision` | enum ApprovalDecision | no | approved / modified / rejected / auto_approved |
| `decision_notes` | Text | yes | |
| `decided_by` | String(120) | yes | user id / "rule_engine" / "system" |
| `decided_at` | DateTime | no | |

Uses `CreatedAtMixin` only.

### `accounting_rules` *(evolves from `categorization_rules`)*

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `rule_name` | String(120) | no | |
| `rule_type` | String(40) | no | vendor / description / amount / event |
| `conditions` | JSONB | no | e.g. `{"match_field":"description","op":"contains","value":"aws"}` |
| `actions` | JSONB | no | e.g. `{"account_id":5320,"confidence":0.85}` |
| `priority` | Int | no | lower runs first |
| `is_system` | bool | no | seeded vs. learned |
| `is_active` | bool | no | default true |

---

## D. Reconciliation

### `reconciliation_matches`

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `bank_transaction_id` | FK bank_transactions | no | |
| `transaction_id` | FK transactions | yes | matched JE |
| `bill_id` / `invoice_id` | FK | yes | matched source doc |
| `payment_allocation_id` | FK payment_allocations | yes | |
| `matched_amount` | Numeric(14,2) | no | |
| `match_type` | String(30) | no | one_to_one / partial / transfer |
| `match_status` | enum MatchStatus | no | |
| `confidence_score` | Float | yes | |

---

## E. Changes to KEEP tables

- `businesses`: add `legal_name` (nullable); `currency` → keep, treat as base currency.
- `vendors`: add `normalized_name`, `default_expense_account_id` (FK accounts, nullable).
- `customers`: add `normalized_name`, `default_revenue_account_id` (FK accounts, nullable).
- `documents`: no structural change required; already close to `source_documents`.
- `document_extractions`: optional add `validation_status`, `prompt_version`.
- `chat_*`, `users`, `audit_logs`: unchanged.

## F. DROP / RETIRE

- `accounts` (old bank-accounts table) — bank accounts become ASSET rows in the new `accounts` chart of accounts.
- `categories` — becomes `accounts`.
- `categorization_rules` — becomes `accounting_rules`.
- `transaction_line_items` — split into `bill_lines` / `invoice_lines`.
- The flat single-entry meaning of `transactions` — data migrates into `bills` / `invoices` / `bank_transactions`, table is reshaped into the JE header.

---

## G. Code that must change when this lands

| Area | File | Change |
|---|---|---|
| P&L | `application/agents/pnl/nodes.py` | rewrite to read `entries × accounts` (revenue/expense account types), not `transactions × categories` |
| Ingestion | `application/services/ingestion_service.py` | on extract, create `bills`/`invoices`/`bank_transactions` (not flat `transactions`); then kick off proposal generation |
| Categorization | `application/agents/categorization/*` | becomes the **proposal** generator: emit `accounting_proposals` + `proposal_lines` instead of writing `category_id` directly |
| Posting | new service | `post_proposal(proposal_id)` → creates `transactions` + `entries`, flips statuses, updates `outstanding_amount` |
| Chat schema | `application/agents/chat/nodes.py` | replace the `SCHEMA` string with the new tables (this is also where deferred skill-loading goes) |
| Summary | `application/services/transaction_service.py` | rewrite aggregates over the ledger |
| Routes | `interface/api/routes/transactions.py` | `transaction` now means a JE; add routes for proposals/approval, bills/invoices |
| Models/Schemas | `domain/models/*`, `domain/schemas/*` | new ORM models + Pydantic schemas + one Alembic migration |

---

## Indexes (for an efficient reporting system)

Reports read `entries` constantly, so index for the rollup + period queries:

- `entries (account_id)` — every balance/trial-balance query groups by this
- `entries (transaction_id)` — fetch a JE's lines; also for the balance CHECK
- `transactions (business_id, status, transaction_date)` — "posted JEs in period" is the hot path for P&L / balance sheet
- `accounts (business_id, parent_account_id)` — hierarchy walk / rollup
- `accounts (business_id, account_type)` — P&L (revenue/expense) vs balance sheet (asset/liability/equity)
- `bank_transactions (fingerprint_hash)` and `(gl_account_id, external_transaction_id)` — dedup
- `bills (business_id, status)`, `invoices (business_id, status)` — AP/AR aging
- `payment_allocations (bill_id)`, `(invoice_id)` — settlement lookups

> **Scale note (later, not now):** at high volume, add an `account_balances` snapshot table (per account, per period) refreshed on post, so reports read one row per account instead of summing all history. Premature today — derive from `entries` until it hurts.

## Decisions — RESOLVED

1. ✅ **Proposals = draft transactions.** `status=PENDING_APPROVAL` → approve → `POSTED`. No separate proposal tables.
2. ✅ **Parallel migration.** New ledger runs alongside the old flat `transactions` during transition; cut over once P&L/chat read the ledger.
3. ✅ **Seed the 3-level consulting COA** (below) in `seeding_service.py`, replacing the 14 flat categories. Posting only at level 3.
