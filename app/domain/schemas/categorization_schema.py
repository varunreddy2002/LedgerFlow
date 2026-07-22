"""Schemas for the AI fallback step of categorization — suggesting an account
for a row (a bank_transaction, or an invoice/bill line during reconciliation)
that couldn't be matched by the deterministic rule engine."""

from pydantic import BaseModel, Field


class AccountSuggestion(BaseModel):
    row_id: int = Field(description="the id of the row this suggestion is for (echoed back from the input)")
    account_code: str | None = Field(
        None, description="the chosen account_code exactly as given in the chart of accounts, or null if none plausibly fits"
    )
    reasoning: str | None = Field(
        None, description="one short sentence explaining the choice, for a human reviewer"
    )


class AccountSuggestions(BaseModel):
    suggestions: list[AccountSuggestion]
