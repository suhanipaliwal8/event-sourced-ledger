import os

import psycopg
import pytest

from fastapi.testclient import TestClient
from urllib.parse import urlsplit, urlunsplit
from app.api.dependencies import get_conn
from app.main import app

from app.db.migrate import apply_migrations
from app.db.connection import connect

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

@pytest.fixture
def ledger_conn(db_url: str):
    """An autocommit connection, like the one the service layer uses."""
    connection = connect(db_url)
    try:
        yield connection
    finally:
        connection.close()

@pytest.fixture
def client(db_url: str):
    """A test HTTP client whose requests use the TEST database."""

    def override_get_conn():
        conn = connect(db_url)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_conn] = override_get_conn
    yield TestClient(app)
    app.dependency_overrides.clear()

APP_ROLE_USER = "ledger_api"
APP_ROLE_PASSWORD = "ledger_api_dev_password"


@pytest.fixture(scope="session")
def app_role_url(db_url: str) -> str:
    """URL of the RESTRICTED login the running application should use."""
    with psycopg.connect(db_url, autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE_USER,)
        ).fetchone()
        if not exists:
            # DDL cannot take bind parameters; these are fixed test constants.
            admin.execute(
                f"CREATE USER {APP_ROLE_USER} PASSWORD '{APP_ROLE_PASSWORD}' IN ROLE ledger_app"
            )

    parts = urlsplit(db_url)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    netloc = f"{APP_ROLE_USER}:{APP_ROLE_PASSWORD}@{host}"
    return urlunsplit(parts._replace(netloc=netloc))


@pytest.fixture
def app_conn(app_role_url: str):
    connection = connect(app_role_url)
    try:
        yield connection
    finally:
        connection.close()