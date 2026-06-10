# LedgerFlow — Backlog

Items that are intentionally deferred. Each entry explains the current
limitation and what the fix looks like when we revisit it.

---

## DuplicateGroup → support fuzzy matching

**Current:** `DuplicateGroup.match_type` accepts `EXACT` and `FUZZY`, but the
upload pipeline only creates groups for exact fingerprint matches (same date +
description + amount).

**Future:** Add a fuzzy pass after exact dedup — compare description similarity
(e.g. Levenshtein distance) and amount proximity within a tolerance window.
This catches cases like "STRIPE PAYOUT" vs "Stripe Transfer" at similar amounts.

---

## DuplicateResolution — per-member keep/exclude UI

**Current:** `DuplicateResolution` has `KEEP_ONE`, `KEEP_ALL`, `EXCLUDE_ALL`.
The resolve endpoint sets `is_kept` on each `DuplicateGroupMember` and
propagates `is_excluded_from_pnl` to the linked transactions.

**Future:** The frontend needs a group review UI that shows all members side by
side and lets the user tick which ones to keep individually.

---

## Accounts endpoint — unmatched account flag

**Current:** If a CSV row has an account name not found in the accounts table,
`account_id` is left null silently.

**Future:** Add `ReviewIssueType.UNMATCHED_ACCOUNT` and create a `ReviewItem`
for each transaction where the CSV had an account name that didn't resolve.

---

## Stripe vs Chase reconciliation

**Current:** Stripe payouts (individual payments) and Chase deposits (bulk
settlements) are treated as independent transactions. No reconciliation logic
exists.

**Future:** Build a reconciliation pass that matches Stripe payout reports
against bank deposit lines within a date tolerance and amount threshold.
This is explicitly NOT duplicate detection — it is many-to-one matching.

---

## Auth — users, passwords, tokens

**Current:** `users` table exists but has no password hash, no token, no
session management. All endpoints are open (no auth).

**Future:** Add `password_hash` to `User`, implement JWT-based auth, protect
all business-scoped endpoints with a `get_current_user` dependency.

---

## LLM categorization (Stage 2)

**Current:** Only rule-based categorization (regex + confidence score).

**Future:** For transactions that remain uncategorized after rule-based pass,
send batches to an LLM for categorization suggestions. Store LLM output as
`confidence_score < 0.75` to always route through human review.

---

## Re-categorization when rules change

**Current:** Adding a new `CategorizationRule` does not retroactively apply to
existing uncategorized transactions.

**Future:** Add a `POST /api/businesses/{id}/recategorize` endpoint that
re-runs the categorization engine on all `needs_review` + `category_id = null`
transactions for the business. Should NOT touch already-categorized rows.

---

## P&L report generation endpoint

**Current:** `pnl_reports` table exists but no route generates or returns a
report.

**Future:** `POST /api/businesses/{id}/pnl-reports` — generate a cash-basis P&L
for a date range from categorized, non-excluded transactions and persist the
snapshot as JSON.
