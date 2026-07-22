"""ledger core rebuild

Retires the old flat transaction/category world and builds the double-entry
ledger core: accounts (real chart of accounts, replacing the old bank-accounts
table of the same name), bank_transactions, transactions + transaction_entries,
accounting_rules, audit_events, invoices/invoice_lines, bills/bill_lines.
Destructive by design (dev DB, data disposable).

Revision ID: 2424c68e4b59
Revises: a0ab2b840a85
Create Date: 2026-07-19 23:08:25.895422

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '2424c68e4b59'
down_revision = 'a0ab2b840a85'
branch_labels = None
depends_on = None


# ── Enum value lists (mirror app.domain.enums; native_enum=False -> VARCHAR+CHECK) ──
_ACCOUNT_TYPE = sa.Enum("asset", "liability", "revenue", "expense", name="accounttype", native_enum=False)
_NORMAL_BALANCE = sa.Enum("debit", "credit", name="normalbalance", native_enum=False)
_BANK_TXN_STATUS = sa.Enum(
    "new", "processing", "review_required", "processed", "excluded", "failed",
    name="banktxnstatus", native_enum=False,
)
_CASH_DIRECTION = sa.Enum("inflow", "outflow", name="cashdirection", native_enum=False)
_TXN_STATUS = sa.Enum(
    "proposed", "review_required", "approved", "rejected", "posted", "reversed", "failed",
    name="transactionstatus", native_enum=False,
)
_INVOICE_BILL_STATUS = sa.Enum("draft", "unpaid", "paid", "void", name="invoicebillstatus", native_enum=False)
_RULE_STATUS = sa.Enum("active", "inactive", "archived", name="rulestatus", native_enum=False)
_PARTY_STATUS = sa.Enum("active", "inactive", name="partystatus", native_enum=False)
_AUDIT_ACTOR_TYPE = sa.Enum("user", "agent", "system", "rule_engine", name="auditactortype", native_enum=False)
_AUDIT_EVENT_TYPE = sa.Enum(
    "created", "extracted", "classified", "modified", "approved", "rejected",
    "posted", "reversed", "reconciled", "failed",
    name="auditeventtype", native_enum=False,
)

_TS = dict(server_default=sa.text("now()"), nullable=False)
_MONEY = sa.Numeric(14, 2)


def upgrade() -> None:
    # ── 1. Drop the old flat-transaction / bank-account / category world ──
    for table in (
        "transaction_line_items",
        "transactions",
        "categorization_rules",
        "categories",
        "accounts",       # old bank-accounts table; replaced by the COA below
        "audit_logs",     # replaced by audit_events
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # ── 2. Extend vendors / customers to the new field names ──
    op.alter_column("vendors", "name", new_column_name="vendor_name")
    op.add_column("vendors", sa.Column("normalized_name", sa.String(length=150), nullable=True))
    op.add_column("vendors", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("vendors", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column("vendors", sa.Column("status", _PARTY_STATUS, server_default="active", nullable=False))
    op.create_index("ix_vendors_normalized_name", "vendors", ["normalized_name"])

    op.alter_column("customers", "name", new_column_name="customer_name")
    op.add_column("customers", sa.Column("normalized_name", sa.String(length=150), nullable=True))
    op.add_column("customers", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("customers", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column("customers", sa.Column("status", _PARTY_STATUS, server_default="active", nullable=False))
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
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["parent_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "account_code", name="uq_accounts_business_code"),
    )
    op.create_index("ix_accounts_business_id", "accounts", ["business_id"])

    # Now that accounts exists, wire the vendor default-account hint.
    op.add_column("vendors", sa.Column("default_account_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_vendors_default_account_id", "vendors", "accounts", ["default_account_id"], ["id"]
    )

    # ── 4. bank_transactions — raw imported rows, source evidence ──
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("external_transaction_id", sa.String(length=120), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("normalized_description", sa.String(length=1024), nullable=True),
        sa.Column("amount", _MONEY, nullable=False),
        sa.Column("direction", _CASH_DIRECTION, nullable=False),
        sa.Column("status", _BANK_TXN_STATUS, server_default="new", nullable=False),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_transactions_business_id", "bank_transactions", ["business_id"])

    # ── 5. transactions — accounting event header ──
    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("status", _TXN_STATUS, server_default="proposed", nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["bank_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_business_id", "transactions", ["business_id"])

    # ── 6. transaction_entries — the debit/credit lines (signed amount) ──
    op.create_table(
        "transaction_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", _MONEY, nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount != 0", name="ck_transaction_entries_amount_nonzero"),
    )
    op.create_index("ix_transaction_entries_transaction_id", "transaction_entries", ["transaction_id"])
    op.create_index("ix_transaction_entries_account_id", "transaction_entries", ["account_id"])

    # ── 7. accounting_rules ──
    op.create_table(
        "accounting_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_name", sa.String(length=120), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=False),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default="100", nullable=False),
        sa.Column("status", _RULE_STATUS, server_default="active", nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_rules_business_id", "accounting_rules", ["business_id"])

    # ── 8. audit_events — append-only, polymorphic by (entity_type, entity_id) ──
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", _AUDIT_EVENT_TYPE, nullable=False),
        sa.Column("actor_type", _AUDIT_ACTOR_TYPE, nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=True),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_business_id", "audit_events", ["business_id"])

    # ── 9. invoices / invoice_lines ──
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=True),
        sa.Column("invoice_number", sa.String(length=60), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", _INVOICE_BILL_STATUS, server_default="draft", nullable=False),
        sa.Column("bank_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("accounting_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["bank_transactions.id"]),
        sa.ForeignKeyConstraint(["accounting_transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_business_id", "invoices", ["business_id"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.SmallInteger(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), server_default="1", nullable=False),
        sa.Column("unit_price", _MONEY, nullable=False),
        sa.Column("tax_amount", _MONEY, server_default="0", nullable=False),
        sa.Column("revenue_account_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["revenue_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    # ── 10. bills / bill_lines ──
    op.create_table(
        "bills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_id", sa.BigInteger(), nullable=True),
        sa.Column("bill_number", sa.String(length=60), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", _INVOICE_BILL_STATUS, server_default="draft", nullable=False),
        sa.Column("bank_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("accounting_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["bank_transactions.id"]),
        sa.ForeignKeyConstraint(["accounting_transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bills_business_id", "bills", ["business_id"])

    op.create_table(
        "bill_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bill_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.SmallInteger(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), server_default="1", nullable=False),
        sa.Column("unit_price", _MONEY, nullable=False),
        sa.Column("tax_amount", _MONEY, server_default="0", nullable=False),
        sa.Column("expense_account_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), **_TS),
        sa.Column("updated_at", sa.DateTime(), **_TS),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"]),
        sa.ForeignKeyConstraint(["expense_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bill_lines_bill_id", "bill_lines", ["bill_id"])


def downgrade() -> None:
    for table in (
        "bill_lines", "bills", "invoice_lines", "invoices",
        "audit_events", "accounting_rules",
        "transaction_entries", "transactions", "bank_transactions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.drop_constraint("fk_vendors_default_account_id", "vendors", type_="foreignkey")
    op.drop_column("vendors", "default_account_id")
    op.drop_table("accounts")

    op.drop_index("ix_customers_normalized_name", table_name="customers")
    op.drop_column("customers", "status")
    op.drop_column("customers", "phone")
    op.drop_column("customers", "email")
    op.drop_column("customers", "normalized_name")
    op.alter_column("customers", "customer_name", new_column_name="name")

    op.drop_index("ix_vendors_normalized_name", table_name="vendors")
    op.drop_column("vendors", "status")
    op.drop_column("vendors", "phone")
    op.drop_column("vendors", "email")
    op.drop_column("vendors", "normalized_name")
    op.alter_column("vendors", "vendor_name", new_column_name="name")

    # Old dropped tables (transaction_line_items/transactions/categorization_rules/
    # categories/accounts/audit_logs) are NOT recreated — data was disposable.
