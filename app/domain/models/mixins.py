"""Reusable column building blocks.

`TimestampMixin` / `CreatedAtMixin` keep the audit-timestamp definitions in one
place (DRY) so every table reports time consistently. `enum_column` renders a
Python Enum as a portable `VARCHAR + CHECK` constraint — SQLite has no native
ENUM type, and storing the `.value` strings keeps the rows human-readable.
`PrimaryKeyMixin` adds a BIGINT auto-increment `id` to every table so the
schema is ready for PostgreSQL migration without changing row values.
"""

import enum
from datetime import datetime
from typing import Optional, Type, TypeVar

from sqlalchemy import BigInteger, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

E = TypeVar("E", bound=enum.Enum)


class PrimaryKeyMixin:
    """BIGINT auto-increment primary key named ``id``.

    Use on every model so SQLite stores 64-bit integers and PostgreSQL
    uses BIGINT — no data changes needed when migrating between the two.
    """

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


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


class ActorMixin:
    """Free-text actor tags ('owner', 'system', 'rule_engine', a user id as a
    string, ...), not a FK to ``users``. There's no auth wired up yet, so this
    can't be enforced or populated automatically — it's here because the design
    doc lists created_by/updated_by on every table, but every value is nullable
    and unused until an actor concept actually exists in the app."""

    created_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
