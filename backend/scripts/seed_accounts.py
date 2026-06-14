"""Seed Chase/Stripe accounts + default categories + rules for business id=1.

Run from the backend folder:
    python scripts/seed_accounts.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.database import SessionLocal
from app.models.business import Account, Business
from app.services.seeding_service import seed_business_defaults

BUSINESS_ID = 1

ACCOUNTS = [
    {
        "account_name": "Chase Checking",
        "account_type": "checking",
        "institution_name": "chase",
        "currency": "USD",
    },
    {
        "account_name": "Stripe Payments",
        "account_type": "stripe",
        "institution_name": "stripe",
        "currency": "USD",
    },
]


def main():
    db = SessionLocal()
    try:
        biz = db.query(Business).filter(Business.id == BUSINESS_ID).first()
        if not biz:
            print(f"ERROR: Business id={BUSINESS_ID} not found. Create it first.")
            return

        print(f"Business: {biz.name}")

        # --- Accounts ---------------------------------------------------------
        print("\n[Accounts]")
        for data in ACCOUNTS:
            existing = (
                db.query(Account)
                .filter(
                    Account.business_id == BUSINESS_ID,
                    Account.institution_name == data["institution_name"],
                )
                .first()
            )
            if existing:
                print(f"  SKIP  {data['account_name']} (id={existing.id})")
            else:
                acct = Account(business_id=BUSINESS_ID, **data)
                db.add(acct)
                db.flush()
                print(f"  OK    {data['account_name']} created (id={acct.id})")

        # --- Categories + Rules -----------------------------------------------
        print("\n[Categories & Rules]")
        seed_business_defaults(db, BUSINESS_ID)

        db.commit()
        print("\nAll done — business is ready for CSV uploads.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
