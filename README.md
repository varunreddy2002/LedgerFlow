# LedgerFlow

A full-stack SaaS finance application for solo entrepreneurs and small businesses.

## Tech Stack

- **Backend**: Python FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL (managed with [uv](https://docs.astral.sh/uv/))
- **Frontend**: React + Vite + TypeScript + Tailwind CSS

## Project Structure

The repository root **is** the backend (Python). The UI lives in `frontend/`.

```
ledgerflow/
  app/
    main.py          # FastAPI app entry point
    core/            # Config and shared utilities
    api/routes/      # Route handlers
    models/          # SQLAlchemy models
    schemas/         # Pydantic schemas
    services/        # Business logic
    agents/          # AI agents (future)
    db/              # Database session and base
  alembic/           # Migrations
  scripts/           # One-off / dev scripts
  pyproject.toml     # Dependencies (source of truth)
  uv.lock            # Fully pinned lockfile
  .env.example
  frontend/
    src/
      components/    # Shared UI components
      pages/         # Page-level components
      api/           # API client functions
      types/         # TypeScript types
    package.json
```

## Running Locally

### Backend

Run everything from the repository root. [uv](https://docs.astral.sh/uv/) manages the
virtual environment and dependencies — no manual `venv`/`pip` needed.

```bash
# Install dependencies into .venv from the lockfile
uv sync

# Copy env file
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# Create the database schema from migrations
uv run alembic upgrade head

# Load demo data (Acme Digital + default categories) — idempotent
uv run python -m app.db.seed

# Start the server
uv run uvicorn app.main:app --reload
```

API available at `http://localhost:8000`  
Health check: `http://localhost:8000/api/health`  
Docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App available at `http://localhost:5173`

### Database Migrations

```bash
# Create a new migration after changing models
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Re-seed demo data (safe to run repeatedly)
uv run python -m app.db.seed
```

> The schema is owned entirely by Alembic. The app does **not** call
> `create_all()`, so the running app and the migration history can never drift.
