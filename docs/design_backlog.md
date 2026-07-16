# LedgerFlow — Design Backlog

Design decisions and gaps captured for later. **Not tonight's scope.** Tonight = ledger core (`accounts` / `journal_entries` / `journal_entry_lines`) + the P&L agent loop. This file is the running record so nothing gets lost.

---

## 1. Classification & posting escalation ladder

Confirmed direction: **deterministic rules → agent fallback → human review → learn.**

```
1. Deterministic rules (accounting_rules) run FIRST — fast, free, auditable.
     • match + confidence ≥ threshold  → auto-approved DRAFT
     • match + confidence < threshold  → review
2. No rule match → the AGENT decides (judgment).
     • agent output → review  (never straight to POSTED)
3. Human reviews / corrects.
4. The correction becomes a NEW accounting_rule.  ← the flywheel
```

**Principles**
- Nothing reaches the **POSTED** books without passing the confidence gate or a human approval. Agent proposals are DRAFT until approved (matches the propose→approve→post design).
- **Large-amount override**: anything over `large_transaction_threshold` always goes to review regardless of confidence (wire the currently-dead config).
- **Step 4 is not optional** — every human decision feeds back as a rule. The deterministic layer grows, the agent is needed less over time. This *is* the learned accounting memory (memory type 2 below).

---

## 2. Unified review / exception queue — the "in-between" gaps

Every seam below follows the **same** pattern (deterministic-try → agent proposes → confidence gate → human decides → feed back). Design **one** exception/review mechanism, not N special cases.

| Gap | Trigger |
|---|---|
| Uncategorized line | no rule match |
| Unmatched party | bill vendor / customer ≠ business name — fixes today's `FAILED` dead-end |
| Ambiguous document type | invoice vs vendor_bill unclear |
| Low extraction confidence | OCR unsure on amount / date / total |
| Suspected duplicate | `fingerprint_hash` hit |
| Unbalanced / invalid posting | proposed entry ≠ balanced, or posts to a non-leaf account |
| New account needed | no fitting COA account → propose creating one (never silent) |
| Payment match | one bank row could settle multiple bills / invoices (reconciliation) |
| Large amount | over `large_transaction_threshold` |

**Recommendation:** a single review/exception abstraction — a *proposal* (from rule or agent) + *confidence* + *type* + *human decision* + *feedback-to-rule*. Generalize the propose→approve→post flow already designed for postings; reuse DRAFT `journal_entries`, `approval_events`, and the `review_status` lifecycle rather than writing bespoke handling for each gap.

---

## 3. Memory (three types)

1. **Conversational** — ✅ have it: LangGraph Postgres checkpointer + `chat_sessions` / `chat_messages`.
2. **Learned accounting** — ✅ in design: `accounting_rules` (the flywheel in §1). Auditable — you can point at *why* the system remembers a mapping.
3. **Semantic / knowledge** — ❌ not built. Vector recall over the business's history (past decisions, owner preferences, prior explanations). `settings` already has Titan embedding config.
   - **Decision: later, not tonight.** Reserve the seam so it's additive: a `recall_memory(query)` tool + a `business_memory` table (`embedding`, `text`, `source_ref`, `kind`). Nothing in the tonight build blocks this.

---

## 4. Design-soon (touches the schema — do before building sources/AP-AR)

- **Posting engine** — the rules that turn a source (bill / invoice / bank row) into a balanced journal entry. The structure is fixed per doc type (bill → Dr expense / Cr AP); the "which expense account" slot is where rules/agent plug in. Tax lines, multi-line allocation.
- **Period close / locking** — `fiscal_periods` + "can't edit a closed month." Required for the `close-management` skill to mean anything.
- **Approval actor / auth** — `approval_events.decided_by` needs a real user identity. Who may approve a posting? RBAC. `users` is a skeleton today.
- **Semantic memory seam** (§3.3).

## 5. Design-later (no core-schema impact)

- Tax handling detail (sales-tax accounts, posting treatment)
- Reversal / correction workflow (reverse + re-post, never edit a posted entry)
- Cash vs accrual basis toggle for reporting
- API surface + frontend for ledger, reports, approvals, and the review queue
- Agent evaluation / accuracy harness (golden datasets, regression on categorization)
- Multi-currency (columns exist; no FX logic)
- Human-review queue UI (surfaces §2)

---

*Keep this list current as decisions are made. Move items into build plans as they're scheduled.*
