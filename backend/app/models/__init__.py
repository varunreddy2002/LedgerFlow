"""Model package.

Importing every model here ensures they are all registered on
`Base.metadata` whenever `app.models` is imported — which is what lets Alembic
autogenerate see the full schema and lets relationship() string references
resolve.
"""

from app.models.audit import AuditLog
from app.models.business import Account, Business, Category, Customer, Vendor
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentExtraction
from app.models.report import PnLReport
from app.models.transaction import (
    CategorizationRule,
    DuplicateCandidate,
    ReviewItem,
    Transaction,
)

__all__ = [
    "AuditLog",
    "Account",
    "Business",
    "Category",
    "Customer",
    "Vendor",
    "ChatMessage",
    "ChatSession",
    "Document",
    "DocumentExtraction",
    "PnLReport",
    "CategorizationRule",
    "DuplicateCandidate",
    "ReviewItem",
    "Transaction",
]
