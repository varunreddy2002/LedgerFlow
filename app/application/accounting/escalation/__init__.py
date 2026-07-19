"""The classification & posting escalation ladder.

deterministic rules → agent fallback → human review, wired as a Chain of
Responsibility. Public surface:

* :func:`build_pipeline` / :class:`CategorizationPipeline` — assemble and run it.
* :class:`LadderOutcome` — the per-row result.
* :class:`AccountClassifier` — the agent seam (implemented by ``BedrockAccountClassifier``).
"""

from app.application.accounting.escalation.context import (  # noqa: F401
    AccountClassifier,
    AccountProposal,
    LadderContext,
    LadderOutcome,
    NullAccountClassifier,
)
from app.application.accounting.escalation.handlers import (  # noqa: F401
    AgentHandler,
    EscalationHandler,
    ReviewHandler,
    RuleHandler,
)
from app.application.accounting.escalation.pipeline import (  # noqa: F401
    CategorizationPipeline,
    build_pipeline,
)
