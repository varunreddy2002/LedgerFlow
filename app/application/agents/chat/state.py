# app/application/agents/chat/state.py
"""Chat graph state.

Two human-in-the-loop branches share the same interrupt mechanism:

* **review approval** — before ``resolve_review_item`` posts anything, the graph
  pauses for the owner to confirm the exact entry (``pending_resolution`` /
  ``review_preview`` / ``review_result``).
* **chart confirmation** — before rendering a generated chart (``chart_*``).
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
    business_id: int

    # review-approval branch (human gate before posting)
    pending_resolution: Optional[dict]
    review_preview: Optional[dict]
    review_result: Optional[dict]

    # chart branch (human gate before rendering)
    chart_description: Optional[str]
    chart_data: Optional[str]
    chart_code: Optional[str]
    chart_confirmed: Optional[bool]
    chart_image: Optional[str]
    chart_error: Optional[str]
    chart_retry_count: int
