from typing import Optional
from typing_extensions import TypedDict


class CategorizationState(TypedDict):
    business_id: int

    pending: list[dict]
    categories: list[dict]
    rules: list[dict]
    unmatched: list[dict]
    assignments: dict[int, dict]