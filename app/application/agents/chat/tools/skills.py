"""load_skill — pull a reusable procedure into context on demand.

Skills are procedural memory (markdown on disk, loaded into an in-memory
registry at startup). The model sees only the catalog (names + descriptions) in
its system prompt; calling this tool returns the full step-by-step body.
"""

from langchain.tools import tool

from app.application.agents.chat.skills import registry


@tool
def load_skill(name: str) -> str:
    """Load a skill's step-by-step procedure. Call this FIRST when a request
    matches one of the skills listed in your system prompt, then follow the
    returned steps (which tools to call, in what order, how to present).

    Args:
        name: the exact skill name from the catalog (e.g. 'generate-profit-and-loss')
    """
    skill = registry.get_skill(name)
    if skill is None:
        return f"No skill named '{name}'. Available skills: {', '.join(registry.all_names())}"
    return skill.body
