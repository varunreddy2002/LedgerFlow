"""Import every ORM model so ``Base.metadata`` is fully populated.

Alembic's ``env.py`` imports this package to discover the schema, and app code
imports concrete models from here. Import order matters only for readability —
SQLAlchemy resolves relationships lazily by class name.
"""

from app.domain.models.business import Business, Vendor, Customer  # noqa: F401
from app.domain.models.document import Document, DocumentExtraction  # noqa: F401
from app.domain.models.ledger import (  # noqa: F401
    Account,
    JournalEntry,
    JournalEntryLine,
    BankTransaction,
    AccountingRule,
    ApprovalEvent,
    ReviewItem,
)
from app.domain.models.chat import ChatSession, ChatMessage  # noqa: F401
from app.domain.models.user import User  # noqa: F401
from app.domain.models.audit import AuditLog  # noqa: F401
