# HANDOVER — Ledger Core + Escalation Ladder + Agentic Chat

Branch: `feat/ledger-core-agentic-chat`. **Everything is left uncommitted** — you
commit personally.

This session built the production-grade vertical slice from
`docs/build_plan_ledger_agentic.md`: a **double-entry ledger**, a
**deterministic → agent → review escalation ladder** that posts bank rows into
balanced journal entries through a **unified review queue**, and a **rebuilt
agentic chat** proving both a P&L request and a categorize → review → approve →
post → learn cycle.

---

## 0. Environment (verified this session)

| Thing | Value |
|---|---|
| Python | `.venv/Scripts/python.exe` (3.11) — the repo venv (global Python lacks langgraph) |
| LangGraph | **1.2.6** (langchain 1.3.11, langgraph-checkpoint-postgres 3.1.0, psycopg 3.3.4) |
| Postgres | 17.2, reachable via `.env` `DATABASE_URL` |
| AWS Bedrock | reachable; chat + agent classifier use `settings.default_chat_model` (Claude Sonnet) |
| pytest | 9.1.1 (installed into the venv this session) |

> Use `.venv/Scripts/python.exe` for everything. `pip` was bootstrapped into the venv
> via `ensurepip` (it was missing).

---

## 1. What changed (high level)

- **Retired** the flat `transactions` world: dropped `transactions`,
  `transaction_line_items`, `categories`, `categorization_rules`, and the old bank
  `accounts` table. Deleted the old `pnl/` and `categorization/` agents,
  `transaction_service.py`, and the flat `transaction` model/schema/route.
- **New ledger core** under `app/application/accounting/` (see
  `docs/IMPLEMENTATION_NOTES.md` for the module-by-module tour):
  `ledger.py`, `journal_entry_builder.py`, `posting_service.py`, `repository.py`,
  `rule_engine.py`, `escalation/`, `review/`, plus `dtos.py`/`errors.py`/`money.py`.
- **New tables** (migration `b1f2c3d4e5a6`): `accounts` (COA), `journal_entries`,
  `journal_entry_lines`, `bank_transactions`, `accounting_rules`, `review_items`,
  `approval_events`.
- **Skills**: `skills/pnl_report.md`, `skills/categorize_review.md`, loaded on demand
  by `app/application/skills.py` (`load_skill` tool + one-line index in the prompt).
- **Rebuilt chat** (`app/application/agents/chat/`): tools `get_pnl`,
  `list_review_items`, `resolve_review_item` (interrupt-gated), `load_skill`,
  `query_ledger`, `request_chart`; concise system prompt (no 100-line schema dump).
- **Intentionally dormant**: file-upload ingestion (`documents/upload` returns 501),
  `ingestion_service.py`, `document_agent.py` — repointed later (see §6).

---

## 2. Migrate + seed (fresh)

```powershell
# from the repo root, with the venv active or via .venv\Scripts\python.exe
.venv\Scripts\python.exe -m alembic upgrade head      # builds the new schema
.venv\Scripts\python.exe scripts\seed_demo.py         # business 1: COA + rules + JEs + bank rows
```

`seed_demo.py` is idempotent. It creates business `id=1` ("Kriwin Consulting"), the
full 3-level consulting chart of accounts (43 accounts, 23 posting leaves), 14
seeded rules, 6 POSTED sample journal entries (so P&L has data immediately), and 7
**UNPROCESSED** bank rows that feed the ladder demo.

> **Clean reset** (data is disposable): `alembic downgrade base` is **not a supported
> path**. The old migration `a0ab2b840a85` had a downgrade bug (shrinking `trans_type`
> to VARCHAR(6), narrower than "receivable") — now **fixed** to VARCHAR(10). But full
> downgrade-to-base still won't work: the destructive migration `b1f2c3d4e5a6`
> intentionally does **not** recreate the old flat `transactions`/`categories` tables
> (data is disposable), so `a0ab2b840a85.downgrade` would then alter a table that no
> longer exists. To reset, drop and recreate the schema instead, then migrate + seed:
> ```powershell
> .venv\Scripts\python.exe -c "from sqlalchemy import text; from app.infrastructure.db.database import engine; c=engine.begin().__enter__(); c.execute(text('DROP SCHEMA public CASCADE')); c.execute(text('CREATE SCHEMA public')); c.commit()"
> .venv\Scripts\python.exe -m alembic upgrade head
> .venv\Scripts\python.exe scripts\seed_demo.py
> ```
> `alembic upgrade head` on a genuinely fresh database was verified clean this session.

---

## 3. Smoke test — deterministic core (no LLM, no AWS)

```powershell
.venv\Scripts\python.exe -m pytest          # 41 tests, all green
```

Covers: P&L rollup + net income, trial balance foots, builder invariants (balanced /
leaves-only / empty / direction consistency), rule engine, the escalation handlers
(auto-post vs. review, large-amount override, direction conflict), and DB-backed
integration (POSTED-only visibility, pipeline split, review resolve → post → learn).
DB-backed tests run in a rolled-back transaction and **skip** if Postgres is down.

**Run the ladder from the CLI** (creates review items + auto-posts):

```powershell
.venv\Scripts\python.exe scripts\run_pipeline.py           # deterministic
.venv\Scripts\python.exe scripts\run_pipeline.py --agent   # + Bedrock agent proposals
```

Expected on the seeded data: **4 auto-posted** (AWS, GitHub, Stripe payout, wire fee),
**3 to review** — one `large_amount` (ADP payroll $12,000, over the $5,000 threshold)
and two `uncategorized` (Riverside, Nimbus).

---

## 4. Smoke test — the two agentic paths (needs AWS Bedrock)

Start the API and talk to business 1 (`POST /api/businesses/1/chat`), or drive the
graph directly in Python. Both were **verified working end-to-end this session**.

**Path A — P&L**
> "What was our profit and loss for calendar year 2026?"

The agent loads the `pnl_report` skill, calls `get_pnl`, and renders a hierarchical,
rolled-up statement. (Seeded baseline before running the ladder: revenue 15,000,
expenses 5,200, net 9,800.)

**Path B — categorize → review → approve → post → learn**
1. Run the ladder (`scripts\run_pipeline.py`) so review items exist.
2. "List my open review items." → agent loads `categorize_review`, calls
   `list_review_items` → shows the 3 items.
3. "Resolve item N: file it under account 5610 (Office & Supplies)." → agent calls
   `resolve_review_item(decision='modified', account_code='5610')`.
4. The graph **interrupts** and returns a preview of the exact entry
   (`Dr 5610 / Cr 1110`). Approve via the resume endpoint
   (`POST /chat/resume {confirmed: true}`).
5. The entry POSTS, the P&L reflects it, and a **learned rule** is created so the
   same vendor auto-files next time.

> HTTP interrupt shape: a chat turn that needs approval returns
> `status: "review_confirm"` (or `"chart_confirm"`) with an `interrupt` payload;
> resume with `POST /api/businesses/{id}/chat/resume` `{session_id, confirmed}`.

---

## 5. Key invariants (enforced in code + tested)

- **Balanced entries only** — `JournalEntryBuilder` refuses unbalanced drafts
  (`UnbalancedEntryError`).
- **Posting to leaves only** — non-leaf accounts rejected (`PostingToNonLeafError`).
- **POSTED-only reports** — the ledger reads only `status=POSTED`; proposals are invisible.
- **Money is never LLM-derived** — the agent/classifier only *chooses an account*;
  amounts come from the bank row, balancing is the builder's job.
- **Nothing posts without the gate** — agent/review resolutions pass the
  `interrupt` human approval before `PostingService.post`. High-confidence
  deterministic rules auto-post (auditable), large amounts never do.
- **Direction consistency** — money-in must credit revenue, money-out must debit an
  expense; a contradiction escalates to review instead of posting.

---

## 6. Intentionally broken / deferred (next session)

- **File ingestion** (CSV/PDF upload) — `documents/upload` returns **501**;
  `ingestion_service.py` + `document_agent.py` are dormant (they still import old
  symbols and are kept off the boot path). Repoint them to create
  `bank_transactions` / bills / invoices, then kick the pipeline.
- **AP/AR + payment matching**, **bills/invoices**, **balance sheet / aging skills**,
  **semantic memory (type 3)**, **auth/RBAC for approvals** (a `"system"`/`"owner"`
  actor string is used today), **period close** — all still deferred.
- **Review-item types**: only `uncategorized` + `large_amount` are fully implemented.
  The other seven are registered as **stubs** (`StubReviewHandler`) — listable, but
  resolving raises `UnsupportedReviewItemTypeError` until a real handler is added.
- **Old migration downgrade bug** (§2) — fix or squash migrations when convenient.
- **Frontend** — not touched; API shapes for accounts/chat changed.

---

## 7. Files to know

| Area | Entry point |
|---|---|
| Ledger math | `app/application/accounting/ledger.py` (`LedgerService`) |
| Posting | `journal_entry_builder.py` + `posting_service.py` |
| Ladder | `escalation/pipeline.py` (`build_pipeline`) → `escalation/handlers.py` |
| Review queue | `review/service.py` (`build_review_service`) → `review/handlers.py` |
| Rules + learning | `rule_engine.py`, `review/rule_learning.py` |
| Skills | `app/application/skills.py`, `skills/*.md` |
| Chat | `agents/chat/{nodes,tool,graph,state,chat,service}.py` |
| Migration | `alembic/versions/b1f2c3d4e5a6_ledger_core_schema.py` |
| Seed | `app/application/services/seeding_service.py`, `scripts/seed_demo.py` |
| Tests | `tests/accounting/*` (run with `pytest`) |
