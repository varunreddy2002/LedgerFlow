"""Shared FastAPI dependencies.

Import from here instead of importing ``get_db`` or ``get_business_or_404``
directly from their source modules — single import point keeps routes clean.
"""

from app.db.database import get_db  # noqa: F401  (re-exported)
from app.api.routes.businesses import get_business_or_404  # noqa: F401  (re-exported)
