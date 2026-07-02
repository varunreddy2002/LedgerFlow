from typing import Optional
from typing_extensions import TypedDict


class PnLState(TypedDict):
    business_id: int
    start_date: str                  # "YYYY-MM-DD"
    end_date: str                    # "YYYY-MM-DD"

    bank_txns: list[dict]            # categorized bank rows in the period
    report: Optional[dict]           # the final P&L output

    gate_failed: bool                # True if uncategorized bank rows blocked it
    uncategorized_count: int         # how many blocked it (for the fail message)