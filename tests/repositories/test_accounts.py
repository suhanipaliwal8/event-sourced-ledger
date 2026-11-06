from uuid import uuid4

from app.domain.account import EXTERNAL_ACCOUNT_ID
from app.repositories.accounts import create_account, get_account


def test_create_and_fetch_account(ledger_conn):
    created = create_account(ledger_conn, "Asha")
    assert get_account(ledger_conn, created.id) == created


def test_get_missing_account_returns_none(ledger_conn):
    assert get_account(ledger_conn, uuid4()) is None


def test_external_account_is_seeded(ledger_conn):
    external = get_account(ledger_conn, EXTERNAL_ACCOUNT_ID)
    assert external is not None
    assert external.kind == "SYSTEM"
    assert external.allow_negative is True