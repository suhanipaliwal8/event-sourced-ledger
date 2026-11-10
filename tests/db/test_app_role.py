from datetime import datetime, timezone

import psycopg
import pytest

from app.domain.money import Money
from app.repositories.accounts import create_account
from app.services.audit_service import get_audit_trail
from app.services.ledger_service import (
    deposit,
    get_balance,
    get_balance_as_of,
    transfer,
    withdraw,
)


def test_app_role_can_run_the_whole_application_flow(app_conn):
    asha = create_account(app_conn, "Asha")
    rahul = create_account(app_conn, "Rahul")
    deposit(app_conn, asha.id, Money(1_000))
    transfer(app_conn, asha.id, rahul.id, Money(300))
    withdraw(app_conn, rahul.id, Money(100))

    assert get_balance(app_conn, asha.id) == Money(700)
    assert get_balance(app_conn, rahul.id) == Money(200)
    assert get_balance_as_of(app_conn, asha.id, datetime.now(timezone.utc)) == Money(700)
    assert get_audit_trail(app_conn, asha.id).integrity.ok


def test_app_role_cannot_update_entries(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("UPDATE entries SET amount = amount")


def test_app_role_cannot_delete_entries(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("DELETE FROM entries")


def test_app_role_cannot_truncate_entries(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("TRUNCATE entries")


def test_app_role_cannot_drop_the_append_only_trigger(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("DROP TRIGGER entries_no_update_delete ON entries")


def test_app_role_cannot_flip_allow_negative(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("UPDATE accounts SET allow_negative = TRUE")


def test_app_role_cannot_create_tables(app_conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("CREATE TABLE evil (id INT)")