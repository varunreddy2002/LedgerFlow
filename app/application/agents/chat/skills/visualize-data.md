---
name: visualize-data
description: Turn query or report results into a chart (trend, comparison, ranking, top-N).
when_to_use: chart, graph, plot, visualize, "show me a graph", trend over time, compare months, top vendors/customers by amount.
---

# Visualize Data

Charts are worth it for trends, comparisons, rankings, or top-N — not for a
single number or a yes/no answer.

1. Get the data FIRST with **query_database** (or **calculate_report** for P&L /
   cash figures). You need the actual JSON rows before you can chart them.

2. Call **request_chart** with:
   - `description`: what to plot, plainly (e.g. "bar chart of expenses by
     category for Q2", "line chart of monthly net cash").
   - `data_json`: the exact JSON string the data tool returned — do not
     re-type or summarize it.

3. The graph then generates the chart code, asks the user to confirm, and
   renders it in a sandbox. You do not write plotting code yourself — just
   request the chart. After it renders, add a one-sentence takeaway of the
   insight (the trend, the biggest mover, etc.).

4. If the user only wants the numbers, skip the chart and answer in text or a
   small table.
