---
name: generate-profit-and-loss
description: Produce a cash-basis profit & loss (income statement) for a period — revenue, expenses, net income.
when_to_use: profit, loss, P&L, income statement, net income, "how much did I make/earn", profitability over a date range.
---

# Generate a Profit & Loss

1. Determine the period (start_date, end_date) from the user's request. If they
   said "last month" / "Q2" / "this year", resolve it to concrete YYYY-MM-DD
   dates. If no period is given, ask the user.

2. Call **calculate_report** with `report_type="pnl"` and the period. Do NOT try
   to compute revenue or expenses yourself with query_database — calculate_report
   returns trusted cash-basis numbers with the correct debit/credit sign handling.

3. Present the result:
   - Lead with the headline: **Net income** = revenue − expenses.
   - Then **Revenue** total, then **Expenses** total.
   - Optionally break down the largest revenue and expense accounts from `lines`
     (each line has account_name and amount). Keep it to the notable ones.
   - Money to 2 decimals, with the currency if known.

4. If revenue and expenses are both zero, the period likely has no _approved_
   transactions yet — say so plainly and suggest reviewing the categorization
   queue (unreviewed items are excluded from a trusted P&L).

5. If the user wants a visual (trend across months, revenue vs expense), you may
   then use request_chart with the report data.
