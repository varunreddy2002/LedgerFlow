"""add invoice fields to documents and tax_collected enum

Revision ID: 383ea72fbdc5
Revises: 894bad8854ec
Create Date: 2026-06-14 19:57:15.596060

"""
from alembic import op
import sqlalchemy as sa


revision = '383ea72fbdc5'
down_revision = '894bad8854ec'
branch_labels = None
depends_on = None


_TRANSACTION_TYPE_VALUES = (
    "'revenue', 'expense', 'transfer', 'owner_draw', 'owner_contribution', "
    "'loan_payment', 'refund', 'tax_payment', 'tax_collected', 'unknown'"
)
_TRANSACTION_TYPE_VALUES_OLD = (
    "'revenue', 'expense', 'transfer', 'owner_draw', 'owner_contribution', "
    "'loan_payment', 'refund', 'tax_payment', 'unknown'"
)

_DROP_CK = """
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = '{table}'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%transaction_type%'
    LOOP
        EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT ' || quote_ident(r.conname);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    # Update transaction_type CHECK constraint to include 'tax_collected'
    for table in ('transactions', 'categorization_rules'):
        op.execute(_DROP_CK.format(table=table))
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_transaction_type "
            f"CHECK (transaction_type IN ({_TRANSACTION_TYPE_VALUES}))"
        )

    op.add_column('documents', sa.Column('invoice_number', sa.String(length=100), nullable=True))
    op.add_column('documents', sa.Column('invoice_date', sa.Date(), nullable=True))
    op.add_column('documents', sa.Column('due_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'due_date')
    op.drop_column('documents', 'invoice_date')
    op.drop_column('documents', 'invoice_number')

    for table in ('transactions', 'categorization_rules'):
        op.execute(_DROP_CK.format(table=table))
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_transaction_type "
            f"CHECK (transaction_type IN ({_TRANSACTION_TYPE_VALUES_OLD}))"
        )
