"""Run the escalation ladder over a business's UNPROCESSED bank rows.

Auto-posts high-confidence rule matches and parks the rest in the review queue.
By default the deterministic path runs (no LLM); pass ``--agent`` to also let the
Bedrock classifier propose accounts for unmatched rows (requires AWS access).

Run from the repo root::

    python scripts/run_pipeline.py            # deterministic only
    python scripts/run_pipeline.py --agent    # with the LLM agent layer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.db.database import session_scope
from app.application.accounting.escalation.pipeline import build_pipeline

BUSINESS_ID = 1


def main() -> None:
    use_agent = "--agent" in sys.argv[1:]
    classifier = None
    if use_agent:
        from app.application.accounting.escalation.agent_classifier import default_classifier
        classifier = default_classifier()

    with session_scope() as db:
        pipeline = build_pipeline(db, BUSINESS_ID, classifier=classifier)
        outcomes = pipeline.run()

    print(f"Processed {len(outcomes)} bank row(s):")
    for o in outcomes:
        detail = (
            f"posted JE {o.journal_entry_id} -> {o.account_code}"
            if o.outcome == "posted"
            else f"review item {o.review_item_id} ({o.item_type})"
        )
        print(f"  bank_txn {o.bank_transaction_id}: {o.outcome:7s} {detail}")
    posted = sum(o.outcome == "posted" for o in outcomes)
    print(f"\nSummary: {posted} auto-posted, {len(outcomes) - posted} sent to review.")


if __name__ == "__main__":
    main()
