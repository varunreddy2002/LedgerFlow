"""Generated cash-basis P&L report snapshots."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.models.mixins import CreatedAtMixin, PrimaryKeyMixin


class PnLReport(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "pnl_reports"

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    revenue_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    cogs_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    gross_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    operating_expenses_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    net_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    # Full line-item breakdown kept as JSON so the snapshot is self-contained.
    report_json: Mapped[Optional[dict]] = mapped_column(JSON)

    business: Mapped["Business"] = relationship()
