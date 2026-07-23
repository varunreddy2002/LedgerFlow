---
name: review-uncategorized-transactions
description: Surface the review queue — bank rows and transactions that need a human decision — and help approve or reclassify them.
when_to_use: review queue, uncategorized, needs review, "what needs my attention", approve transactions, unclassified bank rows.
---

# Review Uncategorized Transactions

The review queue has two kinds of items:

- **bank_transactions** with `status='review_required'` — no rule matched and the
  AI declined (or wasn't confident). No accounting entry exists yet.
- **transactions** with `status='review_required'` — an account was suggested
  (usually by the AI, see `created_by` and `review_notes`) but it is NOT yet
  approved and does NOT count in reports.

1. Pull both lists with **query_database**:

   ```sql
   -- unclassified bank rows
   SELECT id, transaction_date, description, amount, direction
   FROM bank_transactions
   WHERE business_id = :business_id AND status = 'review_required'
   ORDER BY transaction_date;
   ```

   ```sql
   -- suggested-but-unapproved accounting transactions
   SELECT t.id, t.name, t.transaction_date, t.created_by, t.review_notes,
          a.account_name AS suggested_account, te.amount
   FROM transactions t
   JOIN transaction_entries te ON te.transaction_id = t.id
   JOIN accounts a ON a.id = te.account_id
   WHERE t.business_id = :business_id AND t.status = 'review_required'
   ORDER BY t.transaction_date;
   ```

2. Summarise what's waiting: how many of each, and the total dollar amount.
   List the items compactly (date, description, amount, suggested account +
   reasoning where present).

3. For a transaction the user wants to act on, use **transition_transaction**:
   - approve it as suggested, or
   - reclassify it to a different account (they can name the account), or
   - reject it.
   This is a write — it will pause for the user to confirm before committing.

4. Don't approve anything on the user's behalf without them saying so — this
   skill surfaces the queue and acts only on explicit instruction.
