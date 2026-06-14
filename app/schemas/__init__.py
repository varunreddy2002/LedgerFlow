"""Schema package — re-exports for convenient ``from app.schemas import X``."""

from app.schemas.audit_schema import AuditLogBase, AuditLogCreate, AuditLogOut
from app.schemas.business_schema import (
    AccountBase,
    AccountCreate,
    AccountOut,
    BusinessBase,
    BusinessCreate,
    BusinessOut,
    CategoryBase,
    CategoryCreate,
    CategoryOut,
    CustomerBase,
    CustomerCreate,
    CustomerOut,
    VendorBase,
    VendorCreate,
    VendorOut,
)
from app.schemas.chat_schema import (
    ChatMessageBase,
    ChatMessageCreate,
    ChatMessageOut,
    ChatSessionBase,
    ChatSessionCreate,
    ChatSessionOut,
)
from app.schemas.document_schema import (
    DocumentBase,
    DocumentCreate,
    DocumentExtractionBase,
    DocumentExtractionCreate,
    DocumentExtractionOut,
    DocumentOut,
    ParseErrorDetail,
    UploadResponse,
)
from app.schemas.report_schema import PnLReportBase, PnLReportCreate, PnLReportOut
from app.schemas.transaction_schema import (
    CategorizationRuleBase,
    CategorizationRuleCreate,
    CategorizationRuleOut,
    DuplicateGroupBase,
    DuplicateGroupCreate,
    DuplicateGroupMemberBase,
    DuplicateGroupMemberCreate,
    DuplicateGroupMemberOut,
    DuplicateGroupOut,
    ReviewItemBase,
    ReviewItemCreate,
    ReviewItemOut,
    TransactionBase,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.schemas.user_schema import UserBase, UserCreate, UserOut

__all__ = [
    # audit
    "AuditLogBase", "AuditLogCreate", "AuditLogOut",
    # business
    "AccountBase", "AccountCreate", "AccountOut",
    "BusinessBase", "BusinessCreate", "BusinessOut",
    "CategoryBase", "CategoryCreate", "CategoryOut",
    "CustomerBase", "CustomerCreate", "CustomerOut",
    "VendorBase", "VendorCreate", "VendorOut",
    # chat
    "ChatMessageBase", "ChatMessageCreate", "ChatMessageOut",
    "ChatSessionBase", "ChatSessionCreate", "ChatSessionOut",
    # document
    "DocumentBase", "DocumentCreate", "DocumentOut",
    "DocumentExtractionBase", "DocumentExtractionCreate", "DocumentExtractionOut",
    "ParseErrorDetail", "UploadResponse",
    # report
    "PnLReportBase", "PnLReportCreate", "PnLReportOut",
    # transaction
    "CategorizationRuleBase", "CategorizationRuleCreate", "CategorizationRuleOut",
    "DuplicateGroupBase", "DuplicateGroupCreate", "DuplicateGroupOut",
    "DuplicateGroupMemberBase", "DuplicateGroupMemberCreate", "DuplicateGroupMemberOut",
    "ReviewItemBase", "ReviewItemCreate", "ReviewItemOut",
    "TransactionBase", "TransactionCreate", "TransactionOut", "TransactionUpdate",
    # user
    "UserBase", "UserCreate", "UserOut",
]
