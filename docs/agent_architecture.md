# LedgerFlow — Agentic Accounting Architecture (proposed)

Status: **DRAFT — for review.** Pairs with `accounting_schema.md`.

Core principle: **the LLM reasons, plans, and presents. Deterministic code computes. The books are written only through human-approved postings.**

```
 REASON / PLAN / PRESENT   →  LLM (agent node)
 FETCH DATA                →  read-only DB tool
 MONEY MATH (official)     →  ledger primitives  (tested, deterministic)
 AD-HOC SLICING / CHARTS   →  generated code in sandbox (flexible; calls ledger for money)
 WRITE TO BOOKS            →  propose → human approve → post   (never the LLM directly)
```

---

## 1. The `ledger` module — trusted primitives (the heart)

Location: `app/application/accounting/ledger.py`. Pure, deterministic, no LLM. Reads only `status=POSTED` entries. The debit/credit sign convention lives **here, once**. This module is the single source of accounting truth, used by both the report tools and the sandbox.

```python
# ~6 functions. Everything else derives from these.

def balance(business_id, account, as_of=None) -> Decimal:
    """Signed balance of one account in its normal-balance direction.
       account = code ('1110') or id. Sums POSTED entries only."""

def account_tree(business_id, as_of=None) -> AccountNode:
    """Full COA as a tree, each node carrying its rolled-up balance
       (level-3 leaves → level-2 → level-1 via parent_account_id)."""

def pnl(business_id, start, end) -> PnLReport:
    """Cash-/accrual-basis P&L. Revenue + Expense accounts, hierarchical.
       revenue - expenses = net_income. The official number."""

def trial_balance(business_id, as_of) -> TrialBalance:
    """Every account with its debit/credit balance.
       Asserts Σ debit balances == Σ credit balances (books balance)."""

def balance_sheet(business_id, as_of) -> BalanceSheet:
    """Asset / Liability / Equity, hierarchical. Assets == Liab + Equity."""

def ap_aging(business_id, as_of) -> AgingReport:   # open bills by age bucket
def ar_aging(business_id, as_of) -> AgingReport:   # open invoices by age bucket
```

Returns structured objects (dataclasses), not free text. Each report includes the hierarchy so the agent can render an indented, rolled-up view without doing math.

> Why so few? Double-entry is elegant — every statement is "sum entries by account, roll up the tree." Write these once, test them hard, trust them forever.

---

## 2. Tools exposed to the agent — three tiers

**Tier 1 — Deterministic report tools** (thin wrappers over `ledger.*`; the official numbers):
- `get_pnl(start, end)`
- `get_trial_balance(as_of)`
- `get_balance_sheet(as_of)`
- `get_ap_aging(as_of)` / `get_ar_aging(as_of)`
- `get_account_tree()`

**Tier 2 — Data + open-ended analysis:**
- `query_ledger(sql)` — read-only SELECT (you have this as `query_database`)
- `run_analysis(code)` — sandbox exec for ad-hoc pandas; `ledger` + fetched data available, **no write access**
- `request_chart(description, data_json)` — existing chart branch

**Tier 3 — Action (writes, gated):**
- `propose_journal_entry(date, description, lines[])` — creates a **DRAFT** `transactions` + `entries`, returns it for approval. Never posts directly.

The agent picks tools dynamically. Tier 1 for "the books," Tier 2 for "explore," Tier 3 for "record something."

---

## 3. Skills — on-demand playbooks (the token-saver)

A skill = a *workflow playbook* + the subset of tools it needs. Skills are **not** always in context; only a one-line index is.

**Skill file shape** (markdown + frontmatter, or DB row):
```yaml
name: pnl_report
description: Produce a hierarchical P&L for a period with variance narrative
when_to_use: profit/loss, net income, revenue/expense totals, "how did we do"
tools: [get_pnl, get_account_tree, request_chart]
playbook: |
  1. Resolve the period (default: current month).
  2. Call get_pnl(start, end).
  3. Render revenue → expenses → net income, indented by COA hierarchy.
  4. If a prior period is implied, call get_pnl for it too and add variance.
  5. Offer a chart via request_chart.
```

**Loading pattern (fixes the 100-line-SCHEMA-every-turn cost):**
- System prompt always carries: generic accounting grounding + a **lightweight skill index** (`name: description` lines) + a **lightweight tool index**.
- A `load_skill(name)` tool returns the full playbook and activates its tools.
- Agent matches the task → `load_skill` → executes the playbook → answers.

Candidate initial skills (map onto the installed `finance:*` set): `pnl_report`, `balance_sheet`, `reconciliation`, `journal_entry`, `ap_ar_aging`, `variance_analysis`, `month_end_close`.

---

## 4. The chat agent loop (revised graph)

Today: `agent ⇄ run_tools` + a `chart_code_gen → confirm → sandbox` branch.

Revised ReAct loop (same skeleton, new nodes):
```
        ┌─────────────────────────────────────────────┐
        ▼                                             │
      agent ──reason──▶ needs a skill?  ──▶ load_skill ┘
        │
        ├──▶ needs data/report/analysis ──▶ run_tools ──▶ agent
        │
        ├──▶ wants to record a JE ──▶ propose_journal_entry ──▶ approval_interrupt ──▶ agent
        │
        ├──▶ wants a chart ──▶ chart_code_gen → chart_confirm → chart_sandbox → agent   (existing)
        │
        └──▶ done ──▶ respond
```

`approval_interrupt` reuses your existing `interrupt()` human-in-the-loop pattern (same as chart confirm) — the agent proposes a journal entry, the user approves, then it posts. This is the propose→approve→post flow from the schema doc.

---

## 5. Where the sandbox fits (and its guardrails)

The sandbox (your existing Docker `ledger-sandbox`) is the execution environment for `run_analysis(code)` and `request_chart`. Inside it, generated code has:

- `pandas`, `matplotlib`
- a **read-only** `ledger` object (the Tier-1 primitives) — so money math is always the tested function, never improvised
- data passed in / fetched via a **read-only** DB connection
- **no write access, no posting, no `INSERT`/`UPDATE`** — 30s timeout, network-isolated (as today)

Example generated snippet the agent might run:
```python
# "which expense categories grew fastest vs last quarter?"
this_q = ledger.pnl(biz, '2026-04-01', '2026-06-30')
last_q = ledger.pnl(biz, '2026-01-01', '2026-03-31')
df = compare(this_q.expenses, last_q.expenses)   # pandas, not money-critical
return df.sort_values('growth', ascending=False).head(5).to_dict()
```
The *comparison/sorting* is generated and flexible; the *P&L numbers* come from the trusted primitive.

---

## 6. Responsibility split (the one table to remember)

| Concern | Owner | Why |
|---|---|---|
| Understand the question, plan, present | LLM agent | that's what it's good at |
| Fetch rows | read-only DB tool | deterministic, auditable |
| Official statement math (P&L, TB, BS, aging) | `ledger` primitives | must be identical + correct every time |
| Ad-hoc slicing, comparison, viz | generated code in sandbox | logic isn't known ahead of time |
| Writing to the books | propose → approve → post | never let the model post silently |

---

## Open questions for you to weigh in

1. **Where do skill files live** — markdown in a `skills/` dir (git-versioned, easy to edit), or DB rows (editable per-business at runtime)? Playbooks are generic → I lean markdown in the repo; rules stay in the DB.
2. **`run_analysis` scope** — allow it for any ad-hoc question, or keep it behind a confirm like charts? I lean: allow freely for read-only analysis (it can't write), confirm only for charts (visual output).
3. **Skill granularity** — one skill per statement (`pnl_report`, `balance_sheet`…) or a few broader ones (`reporting`, `bookkeeping`, `reconciliation`)? Finer = cleaner routing, more files.
