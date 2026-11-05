# Event-Sourced Ledger

A double-entry bank core where money is modeled as an **immutable stream of events**,
not as a mutable balance column.

## Core idea
- Every balance change is an append-only entry. Nothing is ever updated or deleted.
- Every transaction has entries that sum to zero (double-entry bookkeeping).
- Balances are always derived from history.

## Tech stack
Python 3.12 · FastAPI · PostgreSQL 16 · psycopg 3 · Docker Compose · pytest · GitHub Actions

## Project status
| Phase | Description | Status |
|---|---|---|
| 0 | Project setup, health endpoint, Postgres, CI | Done |
| 1 | Domain model | Planned |
| 2 | Database schema | Planned |
| 3 | Posting transactions | Planned |
| 4 | Derived balances | Planned |
| 5 | REST API | Planned |
| 6 | Point-in-time queries | Planned |
| 7 | Audit trail | Planned |
| 8 | Concurrency | Planned |
| 9 | Idempotency and hardening | Planned |

## Getting started
```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows
pip install -r requirements.txt
docker compose up -d               # start PostgreSQL
uvicorn app.main:app --reload      # run the API
pytest                             # run tests
```

## Endpoints
| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness check |