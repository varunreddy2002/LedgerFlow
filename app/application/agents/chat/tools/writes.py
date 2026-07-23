"""Registry of WRITE tools and their confirm/execute handlers.

A write tool is a signal: the model calls it, ToolNode returns its marker, then
run_tools routes to write_confirm (interrupt) -> write_execute. write_execute
looks the tool up here to summarize (for the confirmation dialog) and to perform
the actual DB mutation only after the user approves.
"""

from app.application.agents.chat.tools.transactions import (
    transition_transaction, summarize_transition, execute_transition,
)
from app.application.agents.chat.tools.configuration import (
    manage_configuration, summarize_configuration, execute_configuration,
)

WRITE_TOOLS = {
    "transition_transaction": {"summarize": summarize_transition, "execute": execute_transition},
    "manage_configuration": {"summarize": summarize_configuration, "execute": execute_configuration},
}

WRITE_TOOL_OBJECTS = [transition_transaction, manage_configuration]
