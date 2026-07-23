---
name: explain-a-number
description: Trace any figure back to what it's made of — where a number comes from, what's inside a total, why it changed.
when_to_use: "where does this number come from", "what's in this total", "break down / explain this figure", "how did you get this", "what makes up my <account/vendor>", "why did X change", tie-out, drill down, itemize a charge.
---

# Explain a Number (where does this figure come from?)

In finance every number must tie back to its source. When the user points at a
figure and asks where it comes from, what's in it, or why it changed, your job is
to **decompose it one level toward the underlying records, show the parts add up,
and offer to go deeper.** Never just restate the number.

1. Pin down what number they mean and where they saw it — a report total, an
   account/category total, a vendor's spend, or a single transaction/charge. If
   it's ambiguous, ask which one before drilling.

2. Break it down using the right source for that kind of number:

   - **A report figure** (net income, total revenue/expenses, a category line):
     call **calculate_report** for the period, then read its `lines` — each
     account's contribution to the total. To go a level deeper, list the
     transactions behind an account (next bullet).

   - **An account or category total** — the transactions that make it up:
     ```sql
     SELECT t.transaction_date, t.name, te.amount, a.account_name
     FROM transaction_entries te
     JOIN transactions t ON t.id = te.transaction_id
     JOIN accounts a ON a.id = te.account_id
     WHERE t.business_id = :business_id
       AND a.account_name ILIKE '%software%'
       AND t.status IN ('approved','posted')
       AND t.transaction_date BETWEEN :start_date AND :end_date
     ORDER BY t.transaction_date;
     ```

   - **A single transaction / charge** — its ledger lines and source bank row,
     then any uploaded bill/invoice line items that itemize it. The bill may be
     unlinked / `review_required`; still use it. Match by vendor name (filename
     or extracted seller/buyer) and roughly by amount/date:
     ```sql
     SELECT d.filename, de.extracted_json->>'seller_name' AS seller,
            bl.description, bl.quantity, bl.unit_price, bl.tax_amount
     FROM bills b
     JOIN documents d ON d.id = b.document_id
     LEFT JOIN document_extractions de ON de.document_id = d.id
     LEFT JOIN bill_lines bl ON bl.bill_id = b.id
     WHERE b.business_id = :business_id
       AND (d.filename ILIKE '%aws%' OR de.extracted_json->>'seller_name' ILIKE '%amazon%')
     ORDER BY bl.line_number;
     ```
     (For money owed to the business, use `invoices` / `invoice_lines` the same way.)

   - **A vendor's total** — the individual bank rows / transactions for that vendor.

3. Show the tie-out: list the components and confirm they sum to the number in
   question. If the user is comparing two periods, pull both and show, line by
   line, what actually drove the change.

4. Offer to drill further — e.g. from a category → to a transaction → to its bill
   line items. Let the user keep asking "and what's in that?".

5. If the next level of detail needs a document that isn't uploaded (e.g. line
   items for a charge with no bill on file), say so plainly — the system has only
   the total — and offer the one in-scope next step: uploading that bill/invoice
   into LedgerFlow. Never point the user outside the app.

6. Stay strictly within this business's accounting the whole time.
