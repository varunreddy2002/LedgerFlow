"""Custom exception hierarchy for the accounting core.

Every failure mode that callers might reasonably want to distinguish gets its
own type, rooted at a small number of base classes so broad `except` clauses
still work. Nothing here is ever swallowed silently — services raise these and
let the boundary (route / chat tool) translate them into a user-facing message.

Hierarchy::

    AccountingError
    ├── LedgerError
    │   ├── UnbalancedEntryError        Σ debits ≠ Σ credits
    │   ├── PostingToNonLeafError       line references a non-posting account
    │   ├── EmptyJournalEntryError      draft has no lines
    │   ├── AccountNotFoundError        account code/id does not exist
    │   └── DirectionConsistencyError   counter side contradicts cash direction
    ├── ReviewError
    │   ├── ReviewItemNotFoundError
    │   └── ReviewItemAlreadyResolvedError
    ├── SkillNotFoundError
    └── EscalationError
"""

from __future__ import annotations


class AccountingError(Exception):
    """Root of every accounting-domain error."""


# ── Ledger / posting ───────────────────────────────────────────────────────
class LedgerError(AccountingError):
    """Base for ledger and posting invariant violations."""


class UnbalancedEntryError(LedgerError):
    """Raised when a journal entry's debits do not equal its credits."""

    def __init__(self, total_debit, total_credit) -> None:
        self.total_debit = total_debit
        self.total_credit = total_credit
        super().__init__(
            f"Journal entry is unbalanced: debits={total_debit} != credits={total_credit} "
            f"(difference={total_debit - total_credit})."
        )


class PostingToNonLeafError(LedgerError):
    """Raised when a line targets an account that is not a posting leaf."""

    def __init__(self, account_code: str) -> None:
        self.account_code = account_code
        super().__init__(
            f"Account {account_code!r} is not a posting leaf; entries may only "
            f"reference level-3 accounts with posting_allowed=True."
        )


class EmptyJournalEntryError(LedgerError):
    """Raised when attempting to build a journal entry with no lines."""

    def __init__(self) -> None:
        super().__init__("A journal entry must have at least one line.")


class AccountNotFoundError(LedgerError):
    """Raised when an account code or id cannot be resolved for a business."""

    def __init__(self, ref) -> None:
        self.ref = ref
        super().__init__(f"No account found for reference {ref!r}.")


class DirectionConsistencyError(LedgerError):
    """Raised when a chosen counter account's type contradicts the cash
    direction (money-in must credit revenue/income; money-out must debit an
    expense) under cash-basis posting."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ── Review queue ───────────────────────────────────────────────────────────
class ReviewError(AccountingError):
    """Base for review-queue errors."""


class ReviewItemNotFoundError(ReviewError):
    def __init__(self, item_id) -> None:
        self.item_id = item_id
        super().__init__(f"Review item {item_id!r} not found.")


class ReviewItemAlreadyResolvedError(ReviewError):
    def __init__(self, item_id) -> None:
        self.item_id = item_id
        super().__init__(f"Review item {item_id!r} is already resolved or dismissed.")


class UnsupportedReviewItemTypeError(ReviewError):
    """Raised when no handler is registered for a review item's type."""

    def __init__(self, item_type) -> None:
        self.item_type = item_type
        super().__init__(f"No handler registered for review item type {item_type!r}.")


# ── Skills ─────────────────────────────────────────────────────────────────
class SkillNotFoundError(AccountingError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No skill named {name!r} is registered.")


# ── Escalation ─────────────────────────────────────────────────────────────
class EscalationError(AccountingError):
    """Base for escalation-ladder failures."""
