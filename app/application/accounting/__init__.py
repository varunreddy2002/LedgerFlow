"""Accounting core: the trusted, deterministic heart of LedgerFlow.

Public surface:

* :class:`~app.application.accounting.ledger.LedgerService` — balances & statements.
* :class:`~app.application.accounting.journal_entry_builder.JournalEntryBuilder` — the
  only way to construct a balanced, leaf-only journal entry.
* :class:`~app.application.accounting.posting_service.PostingService` — the only code
  that writes journal entries (as DRAFT proposals or POSTED entries).
* Repository, DTOs, and the custom error hierarchy.
"""

from app.application.accounting.dtos import (  # noqa: F401
    AccountNode,
    JournalEntryDraft,
    LineDraft,
    PnLReport,
    TrialBalance,
    TrialBalanceRow,
)
from app.application.accounting.errors import (  # noqa: F401
    AccountingError,
    AccountNotFoundError,
    DirectionConsistencyError,
    EmptyJournalEntryError,
    LedgerError,
    PostingToNonLeafError,
    ReviewError,
    ReviewItemNotFoundError,
    SkillNotFoundError,
    UnbalancedEntryError,
)
from app.application.accounting.journal_entry_builder import (  # noqa: F401
    AccountCatalog,
    JournalEntryBuilder,
)
from app.application.accounting.ledger import LedgerService  # noqa: F401
from app.application.accounting.posting_service import PostingService  # noqa: F401
from app.application.accounting.repository import (  # noqa: F401
    AccountRecord,
    LedgerRepository,
    LineTotals,
    SqlAlchemyLedgerRepository,
)
