"""Idempotent seed data: one demo business + a default chart of categories.

Run with:  python -m app.db.seed

Kept as a standalone script (not an Alembic data migration) so it can be re-run
safely against any environment without polluting the schema migration history.
The `get_or_create` guard makes every run idempotent.
"""

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.business import Business, Category
from app.models.enums import CategoryType

DEMO_BUSINESS_NAME = "Acme Digital"

# (name, category_type, parent_category_id) — a starter chart of accounts for a
# solo digital business (freelancer / agency / SaaS-of-one). All top-level for
# now (parent is None); children can be nested later via parent_category_id.
DEFAULT_CATEGORIES: list[tuple[str, CategoryType, int | None]] = [
    # Revenue
    ("Sales Revenue", CategoryType.revenue, None),
    ("Consulting Income", CategoryType.revenue, None),
    ("Subscription Revenue", CategoryType.revenue, None),
    ("Affiliate Income", CategoryType.revenue, None),
    # Cost of goods sold
    ("Hosting & Infrastructure", CategoryType.cogs, None),
    ("Contractor Costs", CategoryType.cogs, None),
    ("Payment Processing Fees", CategoryType.cogs, None),
    # Operating expenses
    ("Software Subscriptions", CategoryType.expense, None),
    ("Advertising & Marketing", CategoryType.expense, None),
    ("Office Supplies", CategoryType.expense, None),
    ("Professional Services", CategoryType.expense, None),
    ("Bank Fees", CategoryType.expense, None),
    ("Travel", CategoryType.expense, None),
    ("Meals & Entertainment", CategoryType.expense, None),
    ("Education & Training", CategoryType.expense, None),
    ("Internet & Phone", CategoryType.expense, None),
    # Equity
    ("Owner Draw", CategoryType.equity, None),
    ("Owner Contribution", CategoryType.equity, None),
    # Non-P&L
    ("Transfer", CategoryType.transfer, None),
    ("Tax Payment", CategoryType.non_pnl, None),
    ("Loan Payment", CategoryType.non_pnl, None),
]


def get_or_create_business(db: Session) -> Business:
    business = db.query(Business).filter(Business.name == DEMO_BUSINESS_NAME).first()
    if business:
        return business
    business = Business(
        name=DEMO_BUSINESS_NAME,
        business_type="digital_services",
        currency="USD",
    )
    db.add(business)
    db.flush()  # assign business.id without ending the transaction
    return business


def seed_default_categories(db: Session, business: Business) -> int:
    existing = {
        name
        for (name,) in db.query(Category.name).filter(
            Category.business_id == business.id
        )
    }
    created = 0
    for name, category_type, parent in DEFAULT_CATEGORIES:
        if name in existing:
            continue
        db.add(
            Category(
                business_id=business.id,
                name=name,
                parent_category_id=parent,
                category_type=category_type,
                is_system=True,
            )
        )
        created += 1
    return created


def run() -> None:
    db = SessionLocal()
    try:
        business = get_or_create_business(db)
        created = seed_default_categories(db, business)
        db.commit()
        print(
            f"Seed complete: business '{business.name}' (id={business.id}), "
            f"{created} new categories added."
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
