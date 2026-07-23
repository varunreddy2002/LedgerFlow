---
name: explain-a-categorization
description: Explain why a transaction was categorized to a particular account — rule vs AI, the reasoning, and the source bank row.
when_to_use: "why was this categorized", explain categorization, how did you classify, why is this in <account>, provenance of a transaction.
---

# Explain a Categorization

1. Identify the transaction. The user may give an id, a name, an amount, or a
   description. If ambiguous, query candidates first and confirm which one.

2. Pull the transaction with its source bank row using **query_database**:

   ```sql
   SELECT t.id, t.name, t.status, t.created_by, t.review_notes,
          t.confidence_score, bt.description AS bank_description,
          bt.normalized_description
   FROM transactions t
   LEFT JOIN bank_transactions bt ON bt.id = t.bank_transaction_id
   WHERE t.business_id = :business_id AND t.id = <the id>;
   ```

3. Pull its ledger lines (which account it hit):

   ```sql
   SELECT te.amount, a.account_code, a.account_name, a.account_type
   FROM transaction_entries te
   JOIN accounts a ON a.id = te.account_id
   WHERE te.transaction_id = <the id>
   ORDER BY te.amount DESC;
   ```

4. Interpret `created_by`:
   - `accounting_rules` → a deterministic keyword rule matched. If useful, show
     the matching rule:
     ```sql
     SELECT rule_name, conditions, actions, priority
     FROM accounting_rules
     WHERE business_id = :business_id AND status = 'active'
     ORDER BY priority;
     ```
     (match `conditions` against the bank row's normalized_description.)
   - `ai_agent:<model>` → the AI fallback suggested it; the reason is in
     `review_notes`. AI suggestions are never auto-approved.

5. Explain in plain language: what the bank row was, which account it was booked
   to, whether a rule or the AI decided it, the reasoning, and its current status
   (approved vs still needs review). If it's still `review_required`, mention it
   is not yet counted in reports and can be approved via the review queue.
