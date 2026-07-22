"""invoices/bills review_required status

Adds REVIEW_REQUIRED to InvoiceBillStatus, for PDF-ingested rows that can't be
fully trusted yet (unresolved vendor/customer, or zero line items extracted).
There's no CHECK constraint enforcing this enum in the DB (validation is
Python-side only, via enum_column's validate_strings) — the only real DDL
change is widening status from VARCHAR(6) (sized for "unpaid") to VARCHAR(15)
(sized for "review_required"), matching bank_transactions/transactions.status
which already carry a REVIEW_REQUIRED value at that width.

Revision ID: 9d4a1f6e2b73
Revises: 7b1f3e9c2a41
Create Date: 2026-07-20 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9d4a1f6e2b73'
down_revision = '7b1f3e9c2a41'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("invoices", "status", type_=sa.String(length=15), existing_nullable=False)
    op.alter_column("bills", "status", type_=sa.String(length=15), existing_nullable=False)


def downgrade() -> None:
    # Narrowing back to 6 would truncate/reject any review_required rows —
    # intentionally left as a no-op; drop them manually first if you need this.
    pass
