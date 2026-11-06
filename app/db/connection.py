import os

import psycopg

# Local development default only (Docker maps host port 5433 -> container 5432).
# Real secrets must never be committed; CI and production use DATABASE_URL.
DEFAULT_DATABASE_URL = (
    "postgresql://ledger:ledger_dev_password@localhost:5433/ledger"
)


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def connect(database_url: str | None = None) -> psycopg.Connection:
    """Open an AUTOCOMMIT connection.

    With autocommit, `with conn.transaction():` starts a real BEGIN and ends with
    a real COMMIT, so our deferred database triggers fire inside the service.
    """
    return psycopg.connect(database_url or get_database_url(), autocommit=True)