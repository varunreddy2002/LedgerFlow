"""Shared pytest fixtures.

The ``db_session`` fixture wraps each test in a real Postgres transaction that is
rolled back at teardown, so integration tests exercise the actual SQLAlchemy
repositories and schema **without** polluting the dev database. If Postgres is not
reachable, DB-backed tests skip (rather than fail) so the pure unit suite still runs
anywhere.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.db.database import engine
from app.domain.models import Business
from app.application.services.seeding_service import seed_business_defaults


@pytest.fixture(scope="session")
def _db_available() -> bool:
    try:
        conn = engine.connect()
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(_db_available):
    """A Session bound to a transaction that is rolled back after the test."""
    if not _db_available:
        pytest.skip("Postgres not reachable; skipping DB-backed integration test")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def seeded_business(db_session) -> int:
    """Create a throwaway business seeded with the full COA, rules, entries and
    bank rows. Rolled back with the surrounding transaction."""
    biz = Business(name="Test Consulting Co", business_type="consulting", currency="USD")
    db_session.add(biz)
    db_session.flush()
    seed_business_defaults(db_session, biz.id)
    db_session.flush()
    return biz.id
