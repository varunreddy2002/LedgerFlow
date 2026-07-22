from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.interface.api.routes.health import router as health_router
from app.interface.api.routes.businesses import router as businesses_router
from app.interface.api.routes.accounts import router as accounts_router
from app.interface.api.routes.documents import router as documents_router
from app.interface.api.routes.chat import router as chat_router
# transactions_router is retired — it targeted the old flat Transaction model,
# which the ledger-core rebuild replaced with transactions/transaction_entries.
# Not wired back in yet; a new router for the ledger shape is future work.

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
app.include_router(chat_router, prefix="/api")


def main() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
