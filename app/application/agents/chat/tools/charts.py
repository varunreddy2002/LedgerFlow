"""request_chart — signal that a chart should be rendered.

This tool does not itself draw anything: returning "chart_requested" tells the
graph's run_tools node to route into the chart branch (code generation -> user
confirmation -> sandboxed rendering).
"""

from langchain.tools import tool


@tool
def request_chart(description: str, data_json: str) -> str:
    """Signal that the user wants a chart. Call query_database FIRST to get the
    data, then pass its JSON result here as data_json. The graph handles code
    generation, user confirmation, and rendering.

    Args:
        description: what the chart should show (e.g. "bar chart of monthly expenses")
        data_json: the JSON string returned by query_database
    """
    return "chart_requested"
