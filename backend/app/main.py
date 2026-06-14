from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.businesses import router as businesses_router
from app.api.routes.accounts import router as accounts_router
from app.api.routes.documents import router as documents_router
from app.api.routes.transactions import router as transactions_router

# Schema is managed by Alembic migrations (run `alembic upgrade head`), not by
# create_all(), so the app and the migration history never disagree.
app = FastAPI(title="LedgerFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(businesses_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
