---
name: pnl_report
description: Produce a hierarchical cash-basis P&L for a period with net income
when_to_use: profit and loss, net income, revenue or expense totals, "how did we do", margins
tools: [get_pnl, get_account_tree]
---

# P&L report playbook

Goal: answer a profit/loss question with the _official_ numbers from the ledger,
rendered as an indented, rolled-up statement. Never compute totals yourself —
`get_pnl` returns the trusted figures and the account hierarchy.

Steps:

1. **Resolve the period.** If the user gave a range, use it. Otherwise default to the
   current calendar year (`2026-01-01` … `2026-12-31`) and say so.
2. **Call `get_pnl(business_id, start_date, end_date)`.** It returns
   `total_revenue`, `total_expenses`, `net_income`, and `revenue` / `expenses`
   subtrees (each node has `account_code`, `account_name`, `balance`, `children`).
3. **Render the statement** top-down, indenting by hierarchy level:
   - Revenue: list each level-2 group and its leaves with amounts, then the revenue total.
   - Expenses: list each level-2 group and its leaves with amounts, then the expense total.
   - End with **Net income = revenue − expenses**. Call out whether it's a profit or loss.
4. **Only report accounts that have a balance.** Zero-balance branches can be omitted.
5. If the user asks _why_ a number looks the way it does, you may call
   `get_account_tree` for context, but do not invent explanations beyond the data.

Guardrails:

- The amounts are cash-basis and reflect only POSTED journal entries. If the user
  expects accrual (unpaid bills/invoices), note that those aren't in these figures.
- Do not post anything or change data in this skill — it is read-only.
