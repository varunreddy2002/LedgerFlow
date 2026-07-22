"""bank_transactions fingerprint dedup

Adds fingerprint_hash to bank_transactions so overlapping/duplicate statement
uploads can be rejected at the DB level via a unique constraint, not just a
pre-insert query. table was empty at migration time -> safe to add NOT NULL
with no backfill.

Revision ID: 7b1f3e9c2a41
Revises: 2424c68e4b59
Create Date: 2026-07-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7b1f3e9c2a41'
down_revision = '2424c68e4b59'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
    )
    op.create_unique_constraint(
        "uq_bank_transactions_business_fingerprint",
        "bank_transactions",
        ["business_id", "fingerprint_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_bank_transactions_business_fingerprint", "bank_transactions", type_="unique"
    )
    op.drop_column("bank_transactions", "fingerprint_hash")
