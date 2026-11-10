import os

import psycopg

# Local development default only (Docker maps host port 5433 -> container 5432).
DEFAULT_DATABASE_URL = (
    "postgresql://ledger:ledger_dev_password@localhost:5433/ledger"
)


def get_database_url() -> str:
    """URL the RUNNING APPLICATION uses.

    In production this must come from DATABASE_URL (the restricted `ledger_api`
    login). Without it, production refuses to start instead of silently using
    a development default.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if os.environ.get("APP_ENV") == "production":
        raise RuntimeError("DATABASE_URL must be set when APP_ENV=production")
    return DEFAULT_DATABASE_URL


def get_migration_database_url() -> str:
    """URL used to RUN MIGRATIONS. It needs owner privileges, so it is kept
    separate from the application's restricted login."""
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if url:
        return url
    return get_database_url()


def connect(database_url: str | None = None) -> psycopg.Connection:
    """Open an AUTOCOMMIT connection.

    With autocommit, `with conn.transaction():` starts a real BEGIN and ends with
    a real COMMIT, so our deferred database triggers fire inside the service.
    """
    return psycopg.connect(database_url or get_database_url(), autocommit=True)