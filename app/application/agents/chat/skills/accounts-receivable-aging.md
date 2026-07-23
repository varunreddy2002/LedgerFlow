---
name: accounts-receivable-aging
description: Show who owes the business money, bucketed by how overdue each unpaid invoice is.
when_to_use: accounts receivable, AR, "who owes me", outstanding invoices, unpaid invoices, overdue customers, aging.
---

# Accounts Receivable Aging

1. Query unpaid invoices with their amounts and due dates using **query_database**.
   Invoice amount is derived (not stored): sum of `quantity*unit_price + tax_amount`
   over its lines. Use:

   ```sql
   SELECT i.invoice_number,
          c.customer_name,
          i.invoice_date,
          i.due_date,
          SUM(il.quantity * il.unit_price + il.tax_amount) AS amount,
          (CURRENT_DATE - i.due_date) AS days_past_due
   FROM invoices i
   JOIN invoice_lines il ON il.invoice_id = i.id
   LEFT JOIN customers c ON c.id = i.customer_id
   WHERE i.business_id = :business_id
     AND i.status = 'unpaid'
   GROUP BY i.id, i.invoice_number, c.customer_name, i.invoice_date, i.due_date
   ORDER BY i.due_date
   ```

2. Bucket each invoice by `days_past_due` (negative = not yet due):
   - **Current** (not yet due, days_past_due <= 0)
   - **1–30 days**
   - **31–60 days**
   - **61–90 days**
   - **90+ days**

3. Present a small aging table: one row per bucket with the count of invoices and
   the total amount, plus a grand total of receivables. Then call out the most
   overdue invoices by name/customer so the user knows who to chase.

4. If there are no unpaid invoices, say the business has no outstanding
   receivables.
