"""AI fallback for categorization — suggests an account for a row (a
bank_transaction, or an invoice/bill line during reconciliation) the
deterministic accounting_rules engine couldn't match.

Runs after the rule pass, on whatever's left over, in small batches (see
`settings.categorization_ai_batch_size`) rather than one call per row. A
suggestion here is never auto-approved by the caller — it only ever produces
a REVIEW_REQUIRED Transaction with the reasoning attached for a human to
check, same as any other guess with no track record yet.
"""

from app.application.agents.document_agent import llm_client
from app.domain.schemas import AccountSuggestions


_PROMPT = """You are an accounting assistant. Some rows (bank transactions,
or invoice/bill line items) had no rule match and need an account suggestion
so a human can review it.

You will be given the business's chart of accounts (postable leaves only —
these are the only valid account_code values) and a batch of unmatched rows,
each with a description and an amount/direction (inflow = money in,
outflow = money out).

For each row, suggest exactly one account_code that best explains what the
money was for. Give one short sentence of reasoning a human reviewer can
quickly check.

If nothing in the chart of accounts plausibly fits, set account_code and
reasoning to null — do not guess just to fill in a value. Return exactly one
suggestion per row given, in any order, using its row_id.
"""


def suggest_accounts(rows: list[dict], accounts: list[dict]) -> AccountSuggestions:
    message = f"Chart of accounts:\n{accounts}\n\nUnmatched rows:\n{rows}"
    return llm_client.invoke_structured(message, _PROMPT, AccountSuggestions)
