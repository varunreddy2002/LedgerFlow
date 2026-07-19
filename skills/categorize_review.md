---
name: categorize_review
description: Work the review queue - list exceptions and approve/correct them to post
when_to_use: review items, categorize transactions, approve, correct, post, uncategorized, large amount, exceptions
tools: [list_review_items, resolve_review_item]
---

# Categorize & review playbook

Goal: help the owner clear the review/exception queue. Each open item is a bank row
the escalation ladder could not auto-post — either no confident rule matched
(`uncategorized`) or the amount exceeded the large-amount threshold (`large_amount`).
Resolving an item posts a balanced journal entry and can teach the system a rule.

Steps:

1. **List the queue.** Call `list_review_items(business_id)`. Each item shows:
   `id`, `item_type`, `description`, `amount`, `source`, and a `proposed_account_code`
   (the rule/agent's best guess, if any).
2. **Present the items** as a short numbered list: what the charge is, the amount,
   and the proposed account. Ask the owner which to approve, correct, or skip.
3. **Resolve one item** with `resolve_review_item`:
   - **Approve the proposal** → `decision="approved"` (posts to `proposed_account_code`).
   - **Correct it** → `decision="modified"`, `account_code="<code>"` (posts to that account
     instead, and learns a rule so the same vendor auto-files next time).
   - **Skip/exclude** → `decision="rejected"` (dismisses the item, no posting).
4. **This is gated.** `resolve_review_item` pauses for the owner's explicit confirmation
   before anything posts — surface the exact entry that will be booked, then wait.
5. After posting, confirm what was booked (account + amount) and whether a rule was learned.

Guardrails:
- You choose the *account*; you never choose the *amount*. The amount always comes from
  the bank row, and the system balances the entry (Dr/Cr) itself.
- For a money-in row the account must be revenue/income; for money-out it must be an
  expense. If the owner names a contradicting account, explain the mismatch and ask again.
- Never resolve an item without the owner's go-ahead.
