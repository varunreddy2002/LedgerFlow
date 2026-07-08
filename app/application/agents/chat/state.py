# app/application/agents/chat/state.py
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
    business_id: int
    chart_description: Optional[str]
    chart_data: Optional[str]
    chart_code: Optional[str]
    chart_confirmed: Optional[bool]
    chart_image: Optional[str]
    chart_error: Optional[str]
    chart_retry_count: int