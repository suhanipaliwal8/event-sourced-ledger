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
| 1 | Domain model (Money, Entry, Transaction) | Done |
| 2 | Database schema, migrations, append-only enforcement | Done |
| 3 | Posting transactions | Planned |
| 4 | Derived balances | Planned |
| 5 | REST API | Planned |
| 6 | Point-in-time queries | Planned |
| 7 | Audit trail | Planned |
| 8 | Concurrency | Planned |
| 9 | Idempotency and hardening | Planned |

## Domain model
The domain layer (`app/domain/`) is pure Python with no database or web dependency.

| Type | Meaning |
|---|---|
| `Money` | Exact amount as an integer in minor units (paise/cents) plus a currency. Floats are rejected. |
| `Entry` | One immutable ledger line: an account and a signed `Money`. |
| `Transaction` | A group of entries that must obey the invariants below. |

**Sign convention:** a positive entry moves money *into* an account, a negative entry moves money *out*.

**Transaction invariants** (checked at construction):
1. At least 2 entries
2. All entries share one currency (multi-currency planned for Phase 11)
3. Entries sum to exactly zero
4. `occurred_at` is timezone-aware
5. Entry amounts are never zero

## Database

```mermaid
erDiagram
    accounts ||--o{ entries : has
    transactions ||--|{ entries : contains
    accounts {
        uuid id PK
        text name
        text kind
        char currency
        bool allow_negative
    }
    transactions {
        uuid id PK
        text description
        text idempotency_key UK
        timestamptz occurred_at
        timestamptz recorded_at
    }
    entries {
        bigint id PK
        uuid transaction_id FK
        uuid account_id FK
        bigint account_version
        bigint amount
    }
```

| Table | Purpose |
|---|---|
| `accounts` | Who can hold money. `allow_negative` is true only for SYSTEM accounts. |
| `transactions` | One immutable row per business event. `occurred_at` = real-world time, `recorded_at` = when saved. |
| `entries` | The ledger events. `(account_id, account_version)` is unique: each account's history is numbered 1, 2, 3, ... |

**Rules enforced by the database itself (defence in depth):**
- `entries` and `transactions` reject `UPDATE`, `DELETE` and `TRUNCATE` (triggers).
- The entries of a transaction must sum to zero, checked **at COMMIT** (deferred constraint trigger).
- A transaction must have at least 2 entries (deferred constraint trigger).
- Entry amounts are never zero; accounts and transactions must exist (CHECK and foreign keys).

### Migrations
Plain SQL files in `migrations/`, applied in filename order and recorded in `schema_migrations`.
**Never edit an applied migration; add a new one.**
```bash
python -m app.db.migrate
```

## Design decisions
- **Integer minor units** instead of floats, to avoid rounding errors.
- **Immutable objects** (frozen dataclasses), matching the append-only model.
- **Layered architecture**: domain (rules) / services / repositories / API.
- **Raw SQL with psycopg** (no ORM), so transactions and locking stay visible.
- **Rules at two levels**: Python domain objects and database triggers.
- **Per-account version numbers** to support optimistic concurrency later.

## Getting started
```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows
pip install -r requirements.txt
docker compose up -d               # start PostgreSQL
docker compose exec db psql -U ledger -d ledger -c "CREATE DATABASE ledger_test;"   # once
python -m app.db.migrate           # create the tables
uvicorn app.main:app --reload      # run the API
pytest                             # run tests (needs PostgreSQL running)
```

## Endpoints
| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness check |

## Git workflow
- One branch per phase: `phase-N/short-name`
- Conventional commit messages (`feat:`, `test:`, `docs:`, `chore:`, `ci:`)
- PRs are merged with a **merge commit** so every commit stays in the history