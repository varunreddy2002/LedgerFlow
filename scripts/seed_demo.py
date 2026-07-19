"""Seed the demo business (id=1) with the full ledger starting point.

Idempotent: creates business 1 if absent, then seeds the chart of accounts,
accounting rules, sample POSTED journal entries, and UNPROCESSED bank rows.

Run from the repo root after ``alembic upgrade head``::

    python scripts/seed_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.db.database import session_scope
from app.domain.models import Business
from app.application.services.seeding_service import seed_business_defaults

BUSINESS_ID = 1


def main() -> None:
    with session_scope() as db:
        biz = db.query(Business).filter(Business.id == BUSINESS_ID).first()
        if biz is None:
            biz = Business(
                id=BUSINESS_ID, name="Kriwin Consulting",
                business_type="consulting", currency="USD",
            )
            db.add(biz)
            db.flush()
            print(f"Created business id={biz.id} ({biz.name})")
        seed_business_defaults(db, BUSINESS_ID)
    print("Seed complete: COA + rules + sample entries + UNPROCESSED bank rows.")


if __name__ == "__main__":
    main()
