import os

import psycopg
import pytest

from app.db.migrate import apply_migrations

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://ledger:ledger_dev_password@localhost:5433/ledger_test",
)


@pytest.fixture(scope="session")
def db_url() -> str:
    """A fresh, fully migrated test database schema, once per test run.

    Entries can never be deleted, so tests cannot clean up after themselves.
    Instead we rebuild the schema at the start, and every test uses new UUIDs.
    """
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
    # Safety guard: never wipe a database that isn't clearly a test database.
    assert db_name.endswith("_test"), f"refusing to reset non-test database {db_name!r}"

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    apply_migrations(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture
def conn(db_url: str):
    """A connection for one test. Anything not committed is rolled back."""
    connection = psycopg.connect(db_url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()