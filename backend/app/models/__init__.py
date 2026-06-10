"""Model package — single import point for all ORM models.

Import order matters here:
  1. user      — referenced by audit, chat, transaction (resolved_by_user_id)
  2. business  — referenced by document, transaction, chat, report, audit
  3. document  — referenced by transaction
  4. transaction — references business, document, user
  5. audit     — references business, user
  6. chat      — references business, user
  7. report    — references business

Importing everything here ensures all models are registered on Base.metadata
so Alembic autogenerate sees the full schema and relationship() string
references resolve correctly at configure time.
"""

from app.models.user import User
from app.models.business import Account, Business, Category, Customer, Vendor
from app.models.document import Document, DocumentExtraction
from app.models.transaction import (
    CategorizationRule,
    DuplicateGroup,
    DuplicateGroupMember,
    ReviewItem,
    Transaction,
)
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, ChatSession
from app.models.report import PnLReport

__all__ = [
    # user
    "User",
    # business
    "Account",
    "Business",
    "Category",
    "Customer",
    "Vendor",
    # document
    "Document",
    "DocumentExtraction",
    # transaction
    "CategorizationRule",
    "DuplicateGroup",
    "DuplicateGroupMember",
    "ReviewItem",
    "Transaction",
    # audit
    "AuditLog",
    # chat
    "ChatMessage",
    "ChatSession",
    # report
    "PnLReport",
]
