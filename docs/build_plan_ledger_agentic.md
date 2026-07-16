# Build Plan — Ledger Core + Escalation Ladder + Agentic Chat

**Branch:** `feat/ledger-core-agentic-chat`
**Execute in:** a fresh session. This doc is the complete brief — read it plus the three design docs before writing any code.

---

## Goal (one sentence)

Build a production-grade vertical slice of the accounting system: a **double-entry ledger**, a **deterministic→agent→review escalation ladder** that posts source rows into balanced journal entries through one **unified review/exception queue**, and an **agentic chat** that proves the loop end-to-end on both a P&L request and a categorize→review→approve→post→learn cycle.

## Design references (read first, in this order)

1. `docs/accounting_schema.md` — table/column specs, enums, invariants, indexes.
2. `docs/agent_architecture.md` — `ledger` primitives, tool tiers, skills, revised loop.
3. `docs/design_backlog.md` — the escalation ladder (§1) and unified review queue (§2). **These are now IN scope for tonight** — build them, don't just reference them.

> **Naming:** use **`accounts`** (COA), **`journal_entries`** (JE header — retire the old flat `transactions`), **`journal_entry_lines`** (lines). Drop the old bank `accounts` table.

---

## Ground rules (decided with the owner — do not re-litigate)

1. **Data is disposable.** Dev DB. Destructive migration is fine — drop old tables and re-seed.
2. **Ingestion (file upload / PDF-OCR / CSV parse) MAY stay broken** — it gets repointed later. But **categorization + posting + review are now IN scope** (that's the ladder). Feed the ladder from **seeded `bank_transactions`**, not from a live upload.
3. **Use the LATEST LangGraph.** Fetch current docs from the web *before* writing the graph. Confirm the version and current API (graph build, tools, `interrupt` HITL, checkpointer). Do not copy the repo's older patterns blindly.
4. **Skills = markdown files** in `skills/`, loaded on demand via `load_skill`. Only a one-line index sits in the system prompt.
5. **Ad-hoc analysis is read-only.** No generated code may write to the DB.
6. **Skill granularity:** one skill per statement / task (`pnl_report`, `categorize_review` first).
7. **Owner runs the smoke test.** Deliverable includes a handover doc with exact run/verify commands. Deterministic code (`ledger`, posting, rule engine) must be unit-tested and passing regardless of whether the chat runs in-session.
8. **NEVER run git commits or pushes.** No `git add`/`commit`/`stash`/`push` under any circumstance. Leave every change in the working tree; the owner commits personally. Use `git status`/`git diff` only to *report*.
9. **Production-grade, senior-dev code.** OOP + design patterns + the Engineering standards below. Hard requirement.

---

## Engineering standards (apply to every task)

Must read like a production system, not a POC.

**OOP & SOLID**
- Real domain concepts as single-responsibility classes. No god-modules, no logic dumped in free functions where an object belongs.
- Depend on abstractions (DIP): services depend on interfaces (`LedgerRepository`, `Skill`, `EscalationHandler`, `ReviewItemHandler` protocols), not on SQLAlchemy or concretes.
- Open/closed: adding a skill, tool, escalation step, or review-item type must not require editing a switch — use registries/polymorphism.
- Encapsulate debit/credit sign rules and posting invariants inside domain objects; callers never touch raw signs.

**Design patterns (named in code + IMPLEMENTATION_NOTES; used where they fit, not forced)**
- **Repository** — account/journal/bank/review data access behind interfaces; domain logic issues no raw inline SQL.
- **Service layer** — `PostingService`, `ReviewQueueService`, `ReportingService` (orchestration) separate from persistence and from domain calc.
- **Chain of Responsibility** — the escalation ladder: `RuleHandler → AgentHandler → ReviewHandler`. Each handler either resolves or passes on.
- **Builder** — `JournalEntryBuilder` that refuses to build unless Σdebit = Σcredit and every account is a posting leaf.
- **Registry** — tool registry, skill registry, and review-item-handler registry (data-driven dispatch, no `if/elif`).
- **Strategy** — per review-item-type resolution behaviour behind a common interface.
- **Command** — LangGraph nodes return commands; routing lives with the node that owns the decision.
- **DTO / value objects** — typed report/proposal results (dataclasses / pydantic), not loose dicts, across boundaries.

**Production concerns**
- Full type hints, `from __future__ import annotations`; clean under any configured type checker.
- Docstrings on every public class/method — purpose, args, invariants. Match house style.
- Logging via existing `get_logger`; structured, leveled (INFO lifecycle, WARNING recoverable, ERROR with context). No `print`. Log at boundaries (tool calls, posting, skill load, escalation decision), not tight loops.
- Custom exception hierarchy: `LedgerError → UnbalancedEntryError, PostingToNonLeafError`; `ReviewError → ReviewItemNotFoundError`; `SkillNotFoundError`. Fail loudly and specifically; never swallow.
- Config via `settings` (incl. `categorization_confidence_threshold`, `large_transaction_threshold` — wire the currently-dead one). No magic numbers. Respect the layered architecture in `CLAUDE.md`.
- Invariants enforced in code, not just docs: balanced entries, posting-to-leaves-only, POSTED-only in reports, confidence gate. Unit-tested.

**LangGraph** — code against the latest web-confirmed API (task 0), not the repo's current version.

---

## Schema for tonight (subset of `accounting_schema.md` + the review queue)

Build these tables (full column specs in `accounting_schema.md`; the new `review_items` is specified here):

- `accounts` (COA, 3-level, posting only at leaves)
- `journal_entries` (JE header, `status`: DRAFT/PENDING_APPROVAL/POSTED/REVERSED)
- `journal_entry_lines` (debit/credit lines + CHECK constraints)
- `bank_transactions` (**minimal** — the source that feeds the ladder; `cash_movement` = debit/credit, `status`, `fingerprint_hash`)
- `accounting_rules` (`conditions`/`actions` JSONB — the deterministic layer + the learned-rule store)
- `approval_events` (references `journal_entries` / `review_items`)
- **`review_items`** (the unified exception queue):

| Column | Type | Null | Notes |
|---|---|---|---|
| `business_id` | FK businesses | no | |
| `item_type` | enum | no | uncategorized / unmatched_party / duplicate / unbalanced / new_account / large_amount / low_extraction / ambiguous_doc / payment_match |
| `status` | enum | no | open / resolved / dismissed |
| `subject_type` | String(40) | no | polymorphic: 'bank_transaction' / 'journal_entry' / … |
| `subject_id` | BigInt | no | id within subject_type |
| `source` | enum | no | rule / agent |
| `confidence` | Float | yes | producer confidence |
| `proposed_resolution` | JSONB | yes | e.g. `{"account_id": 5320, "journal_entry": {...}}` |
| `decision` | enum ApprovalDecision | yes | set on resolve |
| `resolution_notes` | Text | yes | |
| `decided_by` | String(120) | yes | |
| `decided_at` | DateTime | yes | |

Index: `(business_id, status, item_type)`.

---

## Bank → Journal Entry posting rules (cash-basis, tonight) — OWNER-CONFIRMED

The **cash side is always deterministic** — it's the bank row's own GL account (an ASSET, e.g. `1110 Operating Checking`), and the direction fixes the side:

- **Money IN (deposit)** → **Debit Cash** (asset increases)
- **Money OUT (payment)** → **Credit Cash** (asset decreases)

The **counter account is what the escalation ladder classifies** (`RuleHandler → AgentHandler → ReviewHandler`):

| Bank row | Cash side | Counter side (classified) |
|---|---|---|
| Customer payment / direct sale (in) | **Dr** Cash | **Cr** Revenue — e.g. `4110 Consulting Revenue` |
| Interest earned (in) | **Dr** Cash | **Cr** `Interest Income` |
| Vendor / expense payment (out) | **Cr** Cash | **Dr** Expense — e.g. `5320 Cloud Hosting` |
| Bank fee / service charge (out) | **Cr** Cash | **Dr** `5810 Bank Fees Expense` |
| Wire / ACH (in or out) | same as deposit / payment | classified same as above |

**Direction/counter consistency check (enforced by `JournalEntryBuilder`, else escalate to review):**
- money **in** → counter is **credited** → counter must be REVENUE / INCOME (cash-basis)
- money **out** → counter is **debited** → counter must be EXPENSE (cash-basis)
- if a rule/agent picks a counter whose normal-balance side contradicts the direction → **do not post; raise a `review_item`.**

**Deferred to accrual (needs `bills`/`invoices` + payment matching — out of scope tonight):**
- "customer paid an existing invoice" → should Cr **Accounts Receivable**, not Revenue
- "paying an existing vendor bill" → should Dr **Accounts Payable**, not Expense
- Tonight these are booked **cash-basis** (straight to revenue/expense — matches the current P&L basis). A row that clearly settles an open bill/invoice cannot be matched tonight → **flag as a `review_item`, never guess a settlement.**

**Transfers between the business's own accounts** (destination account unknown without the other statement) → **`review_item`**, never booked as revenue/expense.

---

## Tasks (in order). P0 = must land perfectly. P1 = land if core is solid.

### 0 — Prep (P0)
- [ ] Fetch latest LangGraph docs from the web; record version + current API notes for graph/tools/`interrupt`/checkpointer.
- [ ] Confirm Postgres reachable + `.env` (DB URL, AWS Bedrock creds). Record availability for handover.

### 1 — Schema (P0)
- [ ] Enums (schema doc §0) + `ReviewItemType`, `ReviewStatus`, `EscalationSource`.
- [ ] Models: `accounts`, `journal_entries`, `journal_entry_lines`, `bank_transactions` (minimal), `accounting_rules`, `approval_events`, `review_items`.
- [ ] Destructive Alembic migration: drop `categories`, bank `accounts`, flat `transactions`, `transaction_line_items`, old `categorization_rules`; create the new tables + indexes.
- [ ] `alembic upgrade head` clean on a fresh DB.

### 2 — Seed (P0)
- [ ] Full 3-level consulting COA in `seeding_service.py` (every leaf, `posting_allowed` only at level 3, correct `normal_balance`).
- [ ] Seed `accounting_rules` (the vendor→account rules, JSONB form).
- [ ] Seed sample **posted** journal entries (guarantees P&L has data) **and** sample `bank_transactions` in UNPROCESSED status (feeds the ladder demo — include some that match rules, some that don't, and one over `large_transaction_threshold`).

### 3 — Ledger domain module (P0)
- [ ] `app/application/accounting/ledger.py`: `balance`, `account_tree`, `pnl`, `trial_balance`. Sign rules centralized here; reads only `status=POSTED`. Returns typed DTOs carrying hierarchy.
- [ ] `LedgerRepository` interface + SQLAlchemy impl (Repository pattern).
- [ ] Unit tests: `pnl` correct + rolls up the tree; `trial_balance` balances. Must pass in-session.

### 4 — Posting engine (P0)
- [ ] `JournalEntryBuilder` (Builder) — refuses to build unless balanced + all accounts are posting leaves; raises `UnbalancedEntryError`/`PostingToNonLeafError`.
- [ ] `PostingService.post(draft)` → writes `journal_entries`+lines as POSTED; `PostingService.propose(...)` → DRAFT/PENDING_APPROVAL.
- [ ] Unit tests for the invariants (balanced, leaves-only, POSTED-only).

### 5 — Escalation ladder (P0) — Chain of Responsibility
- [ ] `EscalationHandler` protocol; handlers: `RuleHandler` (matches `accounting_rules`, confidence gate + large-amount override) → `AgentHandler` (LLM proposes an account) → `ReviewHandler` (creates a `review_item`).
- [ ] `CategorizationPipeline` wires the chain; input = a `bank_transaction`, output = either an auto-approved DRAFT journal entry (high-confidence rule) or a `review_item`.
- [ ] Feedback loop: resolving a review item with a correction creates a new `accounting_rule` (the flywheel).
- [ ] Unit tests for the deterministic handlers (rule match, threshold gate, large-amount override).

### 6 — Review/exception queue (P0 mechanism, P1 breadth)
- [ ] `ReviewQueueService`: `list(filters)`, `resolve(item_id, decision, correction)` → on approve/correct, build + post the journal entry via `PostingService`, then optionally create a rule.
- [ ] `ReviewItemHandler` registry (Strategy) keyed by `item_type` — **tonight implement `uncategorized` + `large_amount` fully**; register the other types as stubs so the mechanism is generic and they slot in later (P1).
- [ ] Unit tests for `uncategorized` resolve → posts a balanced entry + creates a rule.

### 7 — Skills (P0)
- [ ] `skills/` dir + file format (frontmatter `name`/`description`/`when_to_use`/`tools`; body playbook).
- [ ] `skills/pnl_report.md`, `skills/categorize_review.md`.
- [ ] `load_skill(name)` tool + lightweight skill index in the system prompt.

### 8 — Chat loop, latest LangGraph (P0)
- [ ] Tools: `get_pnl` → `ledger.pnl`; `list_review_items`; `resolve_review_item` (gated by `interrupt` HITL — human approves before posting); `load_skill`.
- [ ] Rebuild the system prompt: accounting grounding + skill index + tool index (drop the always-on 100-line SCHEMA dump).
- [ ] Prove **two** paths end-to-end:
  - P&L: question → `load_skill('pnl_report')` → `get_pnl` → hierarchical report.
  - Ladder: run the pipeline on seeded `bank_transactions` → review items created → chat lists them → human approves via interrupt → entry POSTED → P&L reflects it → correction created a rule.

### 9 — Handover (P0)
- [ ] `docs/HANDOVER.md`: what changed, how to migrate+seed, exact smoke-test steps for both proof paths, what's intentionally broken (file ingestion), next-session TODOs.

### 10 — Self-assessment & engineering write-up (P0, do LAST)
- [ ] `docs/IMPLEMENTATION_NOTES.md`: module-by-module what was built; **design patterns & OOP concepts used, where, and why**; architecture decisions & trade-offs; invariants + how tested; LangGraph version/API notes; candid gaps/shortcuts/tech-debt; next-session TODOs.
- [ ] Honestly mark each Engineering-standard as met / partially met / skipped.
- [ ] Leave everything uncommitted. Summarize to the owner and point at this file.

---

## Definition of done

- App boots; `alembic upgrade head` clean on a fresh DB; new tables seeded (COA + rules + posted entries + bank rows).
- `ledger.pnl`/`trial_balance`, `JournalEntryBuilder`/`PostingService`, and the deterministic escalation handlers are unit-tested and passing.
- The escalation ladder runs on seeded `bank_transactions` and correctly splits into auto-posted drafts vs. `review_items`; large-amount override works.
- Chat proves **both** paths (P&L + categorize→review→approve→post→learn).
- Code meets the Engineering standards (OOP, patterns, logging, typing, custom errors, tests).
- `HANDOVER.md` + `IMPLEMENTATION_NOTES.md` written. **All changes uncommitted.**

## Out of scope tonight (still deferred)

File upload / PDF-OCR / CSV-parse ingestion rewrite · bills / invoices / payments / reconciliation matching · balance sheet & AP/AR skills (P1 stretch) · semantic memory (type 3 — reserve the seam only) · auth / RBAC for approvals (use a `"system"` / stub actor) · period close.

---

## Suggestions, doubts & risk (owner asked for candor)

**This is an ambitious single session.** It's a coherent vertical slice, but it spans schema, a deterministic domain layer, a posting engine, a chained escalation pipeline, a generic review queue, skills, and a rebuilt LangGraph loop. My honest guidance to the build session:

1. **Correctness beats breadth. Land every P0 perfectly before any P1.** A rock-solid ledger + posting engine + one proven gap (`uncategorized`) is worth far more than nine half-wired gap types. That's why the review queue is built **generic (mechanism) but only two item-types are fully implemented tonight** — the rest register as stubs. This is deliberate, not a shortcut.
2. **The money math must never be LLM-derived.** The `AgentHandler` may only *choose an account*; it must never compute amounts or decide balance. Amounts come from the `bank_transaction`; balancing is the `JournalEntryBuilder`'s job. Keep that line bright.
3. **Nothing posts without the human gate.** Agent proposals and review resolutions go through the `interrupt` HITL before `PostingService.post`. A wrong agent guess must be impossible to post silently.
4. **Confirm LangGraph first (task 0).** The loop is central; guessing the API wastes the session. If the latest API differs materially from the repo's, follow the latest and note it in IMPLEMENTATION_NOTES.
5. **If the environment can't run the chat** (no AWS/DB), still deliver: all deterministic layers unit-tested + passing, and a HANDOVER with exact commands so the owner's smoke test proves the LLM paths. Do not fake a green result.
6. **Bank posting — RESOLVED by owner.** Follow the "Bank → Journal Entry posting rules" section above exactly: cash side deterministic (Dr on money-in, Cr on money-out), counter side classified by the ladder, direction/counter consistency enforced by the builder, AR/AP settlement + transfers escalate to review (never guessed) tonight.

---

## Branch & version control

Branch **`feat/ledger-core-agentic-chat`** already exists (off `dev`), planning docs in its working tree.

**Non-negotiable:** the build session works on this branch but runs **no** `git add`/`commit`/`stash`/`push`. The owner performs all commits. Leave every change in the working tree; use `git status`/`git diff` only to report progress.
