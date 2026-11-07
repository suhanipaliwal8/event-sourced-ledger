from uuid import uuid4

import pytest

from app.domain.account import EXTERNAL_ACCOUNT_ID
from app.domain.errors import (
    AccountNotFoundError,
    ConcurrentModificationError,
    CurrencyMismatchError,
    DuplicateTransactionError,
)
from app.domain.money import Money
from app.domain.transaction import Transaction
from app.repositories.accounts import create_account
from app.services import ledger_service
from app.services.ledger_service import deposit, post_transaction


# ---------- helpers ----------
def entries_of(conn, tx_id):
    return conn.execute(
        "SELECT account_id, account_version, amount FROM entries "
        "WHERE transaction_id = %s ORDER BY id",
        (tx_id,),
    ).fetchall()


def transaction_exists(conn, tx_id) -> bool:
    row = conn.execute("SELECT 1 FROM transactions WHERE id = %s", (tx_id,)).fetchone()
    return row is not None


# ---------- happy paths ----------
def test_deposit_creates_two_balanced_entries(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    tx = deposit(ledger_conn, asha.id, Money(10_000))

    rows = entries_of(ledger_conn, tx.id)
    assert len(rows) == 2
    assert sum(r[2] for r in rows) == 0

    by_account = {r[0]: r for r in rows}
    assert by_account[asha.id][1] == 1          # first entry of Asha's history
    assert by_account[asha.id][2] == 10_000
    assert by_account[EXTERNAL_ACCOUNT_ID][2] == -10_000


def test_versions_increase_per_account(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    tx2 = deposit(ledger_conn, asha.id, Money(500))

    versions = {r[0]: r[1] for r in entries_of(ledger_conn, tx2.id)}
    assert versions[asha.id] == 2


def test_transfer_between_customers(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(5_000))

    tx = post_transaction(
        ledger_conn, Transaction.transfer(asha.id, rahul.id, Money(2_000), "rent")
    )

    rows = {r[0]: r for r in entries_of(ledger_conn, tx.id)}
    assert (rows[asha.id][1], rows[asha.id][2]) == (2, -2_000)
    assert (rows[rahul.id][1], rows[rahul.id][2]) == (1, 2_000)


# ---------- rejections ----------
def test_unknown_account_is_rejected_and_nothing_is_written(ledger_conn):
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, uuid4(), Money(100))
    with pytest.raises(AccountNotFoundError):
        post_transaction(ledger_conn, tx)
    assert not transaction_exists(ledger_conn, tx.id)


def test_currency_mismatch_is_rejected(ledger_conn):
    dollar_account = create_account(ledger_conn, "Dollar", currency="USD")
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, dollar_account.id, Money(100, "INR"))
    with pytest.raises(CurrencyMismatchError):
        post_transaction(ledger_conn, tx)
    assert not transaction_exists(ledger_conn, tx.id)


def test_posting_same_transaction_twice_is_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, asha.id, Money(100))
    post_transaction(ledger_conn, tx)
    with pytest.raises(DuplicateTransactionError):
        post_transaction(ledger_conn, tx)
    assert len(entries_of(ledger_conn, tx.id)) == 2   # still only the first posting


# ---------- atomicity and safety net ----------
def test_failure_midway_rolls_back_everything(ledger_conn, monkeypatch):
    """Inject a crash after the FIRST entry is inserted; nothing may remain."""
    asha = create_account(ledger_conn, "Asha")
    real_insert_entry = ledger_service.insert_entry
    calls = {"count": 0}

    def flaky_insert_entry(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated crash")
        return real_insert_entry(*args, **kwargs)

    monkeypatch.setattr(ledger_service, "insert_entry", flaky_insert_entry)

    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, asha.id, Money(1_000))
    with pytest.raises(RuntimeError):
        post_transaction(ledger_conn, tx)

    assert not transaction_exists(ledger_conn, tx.id)
    assert entries_of(ledger_conn, tx.id) == []


def test_stale_version_is_rejected_by_unique_constraint(ledger_conn, monkeypatch):
    """Simulate a racing writer that read an outdated version."""
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))

    monkeypatch.setattr(
        ledger_service, "get_account_state", lambda conn, account_id: (0, 0)
    )

    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, asha.id, Money(500))
    with pytest.raises(ConcurrentModificationError):
        post_transaction(ledger_conn, tx)
    assert not transaction_exists(ledger_conn, tx.id)