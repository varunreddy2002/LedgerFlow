# LedgerFlow

A full-stack SaaS finance application for solo entrepreneurs and small businesses.

## Tech Stack

- **Backend**: Python FastAPI + SQLAlchemy 2.0 + Alembic + SQLite
- **Frontend**: React + Vite + TypeScript + Tailwind CSS

## Project Structure

```
ledgerflow/
  backend/
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
    requirements.txt
    .env.example
  frontend/
    src/
      components/      # Shared UI components
      pages/           # Page-level components
      api/             # API client functions
      types/           # TypeScript types
    package.json
```

## Running Locally

### Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy env file
copy .env.example .env

# Create the database schema from migrations
alembic upgrade head

# Load demo data (Acme Digital + default categories) — idempotent
python -m app.db.seed

# Start the server
uvicorn app.main:app --reload
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
cd backend

# Create a new migration after changing models
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Re-seed demo data (safe to run repeatedly)
python -m app.db.seed
```

> The schema is owned entirely by Alembic. The app does **not** call
> `create_all()`, so the running app and the migration history can never drift.
