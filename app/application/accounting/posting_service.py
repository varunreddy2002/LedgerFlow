"""Persistence for journal entries (Service layer).

`PostingService` is the *only* code that writes journal entries and their lines. It
turns a :class:`JournalEntryDraft` — already proven balanced and leaf-only by the
builder — into ORM rows, so it never re-checks money math. It distinguishes:

* :meth:`propose` — persist as DRAFT / PENDING_APPROVAL (a proposal awaiting the
  human gate); invisible to reports.
* :meth:`post` — persist as POSTED with a timestamp, entry number, and an
  :class:`ApprovalEvent` audit record; now visible to reports.

Nothing here calls an LLM, and nothing posts without a caller that has passed the
human interrupt gate (or a high-confidence deterministic rule).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import ApprovalDecision, JournalEntryStatus
from app.domain.models.ledger import ApprovalEvent, JournalEntry, JournalEntryLine
from app.application.accounting.dtos import JournalEntryDraft

logger = get_logger(__name__)


class PostingService:
    """Writes journal entries. One instance per unit of work (wraps a Session)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── proposal (draft, not in the books) ─────────────────────────────────
    def propose(
        self,
        draft: JournalEntryDraft,
        *,
        status: JournalEntryStatus = JournalEntryStatus.PENDING_APPROVAL,
    ) -> JournalEntry:
        """Persist a draft as a proposal (DRAFT or PENDING_APPROVAL). Not posted."""
        if status not in (JournalEntryStatus.DRAFT, JournalEntryStatus.PENDING_APPROVAL):
            raise ValueError(f"propose() status must be a draft state, got {status!r}")
        entry = self._materialize(draft, status)
        self._session.flush()
        logger.info(
            "[posting.propose] journal_entry_id=%s status=%s lines=%d total=%s",
            entry.id, status.value, len(entry.lines), draft.total_debit,
        )
        return entry

    # ── posting (into the books) ────────────────────────────────────────────
    def post(
        self,
        draft: JournalEntryDraft,
        *,
        decided_by: str = "system",
        decision: ApprovalDecision = ApprovalDecision.AUTO_APPROVED,
        notes: Optional[str] = None,
    ) -> JournalEntry:
        """Persist a draft as a POSTED entry and record the approval event.

        The caller is responsible for having cleared the human gate (or matched a
        high-confidence deterministic rule). This method assigns ``posted_at`` and a
        human-readable ``entry_number`` and writes an immutable :class:`ApprovalEvent`.
        """
        entry = self._materialize(draft, JournalEntryStatus.POSTED)
        entry.posted_at = datetime.utcnow()
        self._session.flush()  # assign id
        entry.entry_number = f"JE-{entry.id:06d}"

        self._session.add(ApprovalEvent(
            journal_entry_id=entry.id,
            decision=decision,
            decision_notes=notes,
            decided_by=decided_by,
        ))
        self._session.flush()
        logger.info(
            "[posting.post] POSTED journal_entry_id=%s number=%s by=%s decision=%s total=%s",
            entry.id, entry.entry_number, decided_by, decision.value, draft.total_debit,
        )
        return entry

    def post_proposal(
        self,
        entry: JournalEntry,
        *,
        decided_by: str = "system",
        decision: ApprovalDecision = ApprovalDecision.APPROVED,
        notes: Optional[str] = None,
    ) -> JournalEntry:
        """Flip an existing DRAFT/PENDING proposal to POSTED (no new lines).

        Used when a proposal was persisted first (e.g. surfaced for approval) and is
        approved as-is. Re-posting an already-POSTED entry is a no-op-safe guard.
        """
        if entry.status is JournalEntryStatus.POSTED:
            logger.warning("[posting.post_proposal] entry %s already posted", entry.id)
            return entry
        entry.status = JournalEntryStatus.POSTED
        entry.posted_at = datetime.utcnow()
        if not entry.entry_number:
            entry.entry_number = f"JE-{entry.id:06d}"
        self._session.add(ApprovalEvent(
            journal_entry_id=entry.id,
            decision=decision,
            decision_notes=notes,
            decided_by=decided_by,
        ))
        self._session.flush()
        logger.info(
            "[posting.post_proposal] POSTED journal_entry_id=%s by=%s decision=%s",
            entry.id, decided_by, decision.value,
        )
        return entry

    # ── internals ────────────────────────────────────────────────────────────
    def _materialize(
        self, draft: JournalEntryDraft, status: JournalEntryStatus
    ) -> JournalEntry:
        """Create the ORM header + lines from a draft, add to the session."""
        entry = JournalEntry(
            business_id=draft.business_id,
            journal_type=draft.journal_type,
            entry_date=draft.entry_date,
            effective_date=draft.entry_date,
            description=draft.description,
            event_type=draft.event_type,
            status=status,
            source=draft.source,
            confidence_score=draft.confidence_score,
            source_document_id=draft.source_document_id,
        )
        for seq, line in enumerate(draft.lines, start=1):
            entry.lines.append(JournalEntryLine(
                account_id=line.account_id,
                sequence_number=seq,
                description=line.description,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                reason_code=line.reason_code,
                confidence_score=line.confidence_score,
            ))
        self._session.add(entry)
        return entry
