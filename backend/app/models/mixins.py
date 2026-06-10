"""Reusable column building blocks.

`TimestampMixin` / `CreatedAtMixin` keep the audit-timestamp definitions in one
place (DRY) so every table reports time consistently. `enum_column` renders a
Python Enum as a portable `VARCHAR + CHECK` constraint — SQLite has no native
ENUM type, and storing the `.value` strings keeps the rows human-readable.
"""

import enum
from datetime import datetime
from typing import Type, TypeVar

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

E = TypeVar("E", bound=enum.Enum)


def enum_column(enum_cls: Type[E], **kwargs):
    """A VARCHAR column constrained to an Enum's values, portable across DBs."""
    return mapped_column(
        Enum(
            enum_cls,
            native_enum=False,  # emit VARCHAR + CHECK instead of a DB ENUM type
            validate_strings=True,
            values_callable=lambda e: [member.value for member in e],
        ),
        **kwargs,
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
