"""Chat tool surface — small and stable, one file per tool.

This module is the single source of truth for what the agent can call:

    ALL_TOOLS      -> bound to the model AND executed by the graph's ToolNode
    TOOL_REGISTRY  -> name -> tool, for direct lookups / routing decisions

New tools are added by creating a file here and appending to ALL_TOOLS — the
graph wiring in nodes.py never has to change.
"""

from app.application.agents.chat.tools.query import query_database
from app.application.agents.chat.tools.reports import calculate_report
from app.application.agents.chat.tools.skills import load_skill
from app.application.agents.chat.tools.transactions import transition_transaction
from app.application.agents.chat.tools.configuration import manage_configuration
from app.application.agents.chat.tools.memory import remember, recall
from app.application.agents.chat.tools.charts import request_chart

ALL_TOOLS = [
    query_database, calculate_report, load_skill,
    transition_transaction, manage_configuration,
    remember, recall, request_chart,
]
TOOL_REGISTRY = {t.name: t for t in ALL_TOOLS}

__all__ = [
    "ALL_TOOLS", "TOOL_REGISTRY",
    "query_database", "calculate_report", "load_skill",
    "transition_transaction", "manage_configuration",
    "remember", "recall", "request_chart",
]
