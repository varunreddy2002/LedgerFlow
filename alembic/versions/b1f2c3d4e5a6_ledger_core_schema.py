"""ledger core schema — retire flat transactions, build double-entry ledger

Destructive by design (dev DB, data disposable): drops the old flat
``transactions`` world and the old bank ``accounts`` / ``categories`` tables,
then creates the double-entry ledger core plus the unified review queue.

Revision ID: b1f2c3d4e5a6
Revises: a0ab2b840a85
Create Date: 2026-07-16

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b1f2c3d4e5a6"
down_revision = "a0ab2b840a85"
branch_labels = None
depends_on = None


# ── Enum value lists (mirror app.domain.enums; native_enum=False → VARCHAR+CHECK) ──
_ACCOUNT_TYPE = sa.Enum(
    "asset", "liability", "equity", "revenue", "expense",
    name="accounttype", native_enum=False,
)
_NORMAL_BALANCE = sa.Enum("debit", "credit", name="normalbalance", native_enum=False)
_JOURNAL_TYPE = sa.Enum(
    "general", "sales", "purchase", "bank", "adjustment",
    name="journaltype", native_enum=False,
)
_EVENT_TYPE = sa.Enum(
    "bill", "invoice", "payment", "adjustment", "opening_balance", "manual",
    name="txneventtype", native_enum=False,
)
_JE_STATUS = sa.Enum(
    "draft", "pending_approval", "posted", "reversed",
    name="journalentrystatus", native_enum=False,
)
_BANK_STATUS = sa.Enum(
    "unprocessed", "proposed", "posted", "excluded",
    name="banktxnstatus", native_enum=False,
)
_APPROVAL_DECISION = sa.Enum(
    "approved", "modified", "rejected", "auto_approved",
    name="approvaldecision", native_enum=False,
)
_REVIEW_ITEM_TYPE = sa.Enum(
    "uncategorized", "unmatched_party", "duplicate", "unbalanced", "new_account",
    "large_amount", "low_extraction", "ambiguous_doc", "payment_match",
    name="reviewitemtype", native_enum=False,
)
_REVIEW_STATUS = sa.Enum("open", "resolved", "dismissed", name="reviewstatus", native_enum=False)
_ESCALATION_SOURCE = sa.Enum("rule", "agent", name="escalationsource", native_enum=False)

_TS = dict(server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # ── 1. Drop the old flat-transaction world (CASCADE handles FK order) ──
    for table in (
        "transaction_line_items",
        "transactions",
        "categorization_rules",
        "categories",
        "accounts",          # old bank-accounts table; replaced by the COA below
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # ── 2. Extend kept tables ──
    op.add_column("businesses", sa.Column("legal_name", sa.String(length=200), nullable=True))
    op.add_column("vendors", sa.Column("normalized_name", sa.String(length=150), nullable=True))
    op.add_column("customers", sa.Column("normalized_name", sa.String(length=150), nullable=True))
    op.create_index("ix_vendors_normalized_name", "vendors", ["normalized_name"])
    op.create_index("ix_customers_normalized_name", "customers", ["normalized_name"])

    # ── 3. accounts — chart of accounts (self-referential tree) ──
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("account_code", sa.String(length=10), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("account_type", _ACCOUNT_TYPE, nullable=False),
        sa.Column("account_subtype", sa.String(length=50), nullable=True),
        sa.Column("parent_account_id", sa.BigInteger(), nullable=True),
        sa.Column("hierarchy_level", sa.SmallInteger(), nullable=False),
        sa.Column("normal_balance", _NORMAL_BALANCE, nullable=False),
        sa.Column("posting_allowed", sa.Boolean(), nullable=False),
        sa.Column("is_control_account", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["parent_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "account_code", name="uq_accounts_business_code"),
    )
    op.create_index("ix_accounts_business_id", "accounts", ["business_id"])
    op.create_index("ix_accounts_business_parent", "accounts", ["business_id", "parent_account_id"])
    op.create_index("ix_accounts_business_type", "accounts", ["business_id", "account_type"])

    # ── 4. journal_entries — JE header ──
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("journal_type", _JOURNAL_TYPE, nullable=False),
        sa.Column("entry_number", sa.String(length=30), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("event_type", _EVENT_TYPE, nullable=False),
        sa.Column("status", _JE_STATUS, nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("source", _ESCALATION_SOURCE, nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("source_document_id", sa.BigInteger(), nullable=True),
        sa.Column("reverses_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["reverses_entry_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entries_business_id", "journal_entries", ["business_id"])
    op.create_index(
        "ix_journal_entries_biz_status_date",
        "journal_entries",
        ["business_id", "status", "entry_date"],
    )

    # ── 5. journal_entry_lines — the debit/credit lines ──
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("journal_entry_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence_number", sa.SmallInteger(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("debit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("credit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason_code", sa.String(length=60), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("debit_amount >= 0", name="ck_jel_debit_nonneg"),
        sa.CheckConstraint("credit_amount >= 0", name="ck_jel_credit_nonneg"),
        sa.CheckConstraint("NOT (debit_amount > 0 AND credit_amount > 0)", name="ck_jel_one_side"),
        sa.CheckConstraint("debit_amount > 0 OR credit_amount > 0", name="ck_jel_nonempty"),
    )
    op.create_index("ix_jel_account", "journal_entry_lines", ["account_id"])
    op.create_index("ix_jel_journal_entry", "journal_entry_lines", ["journal_entry_id"])

    # ── 6. bank_transactions — raw imported rows that feed the ladder ──
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("gl_account_id", sa.BigInteger(), nullable=False),
        sa.Column("source_document_id", sa.BigInteger(), nullable=True),
        sa.Column("journal_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("external_transaction_id", sa.String(length=120), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("normalized_description", sa.String(length=1024), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cash_movement", _NORMAL_BALANCE, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=True),
        sa.Column("status", _BANK_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["gl_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_txn_business_id", "bank_transactions", ["business_id"])
    op.create_index("ix_bank_txn_biz_status", "bank_transactions", ["business_id", "status"])
    op.create_index("ix_bank_txn_fingerprint", "bank_transactions", ["fingerprint_hash"])
    op.create_index(
        "ix_bank_txn_external", "bank_transactions", ["gl_account_id", "external_transaction_id"]
    )

    # ── 7. accounting_rules — deterministic + learned classification ──
    op.create_table(
        "accounting_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_name", sa.String(length=120), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=False),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_rules_business_id", "accounting_rules", ["business_id"])
    op.create_index(
        "ix_accounting_rules_biz_active_priority",
        "accounting_rules",
        ["business_id", "is_active", "priority"],
    )

    # ── 8. review_items — the unified exception queue ──
    op.create_table(
        "review_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("item_type", _REVIEW_ITEM_TYPE, nullable=False),
        sa.Column("status", _REVIEW_STATUS, nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("source", _ESCALATION_SOURCE, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("proposed_resolution", postgresql.JSONB(), nullable=True),
        sa.Column("decision", _APPROVAL_DECISION, nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_items_business_id", "review_items", ["business_id"])
    op.create_index(
        "ix_review_items_biz_status_type", "review_items", ["business_id", "status", "item_type"]
    )

    # ── 9. approval_events — audit trail (after review_items for its FK) ──
    op.create_table(
        "approval_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("journal_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("review_item_id", sa.BigInteger(), nullable=True),
        sa.Column("decision", _APPROVAL_DECISION, nullable=False),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(), **_TS),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_events_journal_entry_id", "approval_events", ["journal_entry_id"])
    op.create_index("ix_approval_events_review_item_id", "approval_events", ["review_item_id"])


def downgrade() -> None:
    # Destructive forward migration; downgrade drops the ledger core. The old
    # flat-transaction tables are NOT recreated (data was disposable by design).
    for table in (
        "approval_events",
        "review_items",
        "accounting_rules",
        "bank_transactions",
        "journal_entry_lines",
        "journal_entries",
        "accounts",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.drop_index("ix_customers_normalized_name", table_name="customers")
    op.drop_index("ix_vendors_normalized_name", table_name="vendors")
    op.drop_column("customers", "normalized_name")
    op.drop_column("vendors", "normalized_name")
    op.drop_column("businesses", "legal_name")
