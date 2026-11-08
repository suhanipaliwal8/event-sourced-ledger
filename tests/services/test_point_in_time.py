import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.account import EXTERNAL_ACCOUNT_ID
from app.domain.errors import AccountNotFoundError, FutureTransactionError
from app.domain.money import Money
from app.domain.transaction import Transaction
from app.repositories.accounts import create_account
from app.services.ledger_service import (
    deposit,
    get_balance,
    get_balance_as_of,
    post_transaction,
    withdraw,
)


def ago(**kwargs) -> datetime:
    """A timezone-aware moment in the past, e.g. ago(days=3)."""
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def recorded_at(conn, tx_id) -> datetime:
    return conn.execute(
        "SELECT recorded_at FROM transactions WHERE id = %s", (tx_id,)
    ).fetchone()[0]


def transaction_exists(conn, tx_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM transactions WHERE id = %s", (tx_id,)
    ).fetchone() is not None


# ---------- time travel with occurred_at ----------
def test_balance_before_any_entry_is_zero(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=3))
    assert get_balance_as_of(ledger_conn, asha.id, ago(days=4)) == Money(0)


def test_balance_between_transactions(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=3))
    deposit(ledger_conn, asha.id, Money(500), occurred_at=ago(days=1))

    assert get_balance_as_of(ledger_conn, asha.id, ago(days=2)) == Money(1_000)
    assert get_balance_as_of(ledger_conn, asha.id, ago(days=0)) == Money(1_500)


def test_as_of_is_inclusive(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    moment = ago(days=2)
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=moment)
    assert get_balance_as_of(ledger_conn, asha.id, moment) == Money(1_000)


def test_withdrawals_reduce_historical_balance(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=3))
    withdraw(ledger_conn, asha.id, Money(400), occurred_at=ago(days=1))

    assert get_balance_as_of(ledger_conn, asha.id, ago(days=2)) == Money(1_000)
    assert get_balance_as_of(ledger_conn, asha.id, ago(days=0)) == Money(600)


def test_balance_as_of_now_equals_current_balance(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=3))
    deposit(ledger_conn, asha.id, Money(500), occurred_at=ago(days=1))
    withdraw(ledger_conn, asha.id, Money(200))

    now = datetime.now(timezone.utc)
    assert get_balance_as_of(ledger_conn, asha.id, now) == get_balance(ledger_conn, asha.id)


def test_other_accounts_do_not_affect_the_result(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, rahul.id, Money(9_000), occurred_at=ago(days=1))

    now = datetime.now(timezone.utc)
    assert get_balance_as_of(ledger_conn, asha.id, now) == Money(0)


# ---------- backdating and "what did we know then" ----------
def test_backdated_transaction_changes_historical_balance(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=1))   # posted first
    deposit(ledger_conn, asha.id, Money(500), occurred_at=ago(days=5))     # posted second, but older

    assert get_balance_as_of(ledger_conn, asha.id, ago(days=4)) == Money(500)
    assert get_balance_as_of(ledger_conn, asha.id, ago(days=0)) == Money(1_500)


def test_known_at_hides_entries_recorded_later(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    tx1 = deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=3))
    books_closed = recorded_at(ledger_conn, tx1.id)
    time.sleep(0.05)
    # Discovered later, but it really happened 2 days ago.
    deposit(ledger_conn, asha.id, Money(500), occurred_at=ago(days=2))

    as_of = ago(days=1)
    # What we know TODAY about that moment:
    assert get_balance_as_of(ledger_conn, asha.id, as_of) == Money(1_500)
    # What our books SAID right after the first deposit was recorded:
    assert get_balance_as_of(ledger_conn, asha.id, as_of, known_at=books_closed) == Money(1_000)


# ---------- rejections ----------
def test_unknown_account_raises(ledger_conn):
    with pytest.raises(AccountNotFoundError):
        get_balance_as_of(ledger_conn, uuid4(), datetime.now(timezone.utc))


def test_naive_as_of_is_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    with pytest.raises(ValueError):
        get_balance_as_of(ledger_conn, asha.id, datetime(2026, 1, 1))


def test_future_dated_transaction_is_rejected_and_nothing_is_written(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, asha.id, Money(100), occurred_at=tomorrow)

    with pytest.raises(FutureTransactionError):
        post_transaction(ledger_conn, tx)

    assert not transaction_exists(ledger_conn, tx.id)
    assert get_balance(ledger_conn, asha.id) == Money(0)


# ---------- known limitation, pinned down on purpose ----------
def test_backdated_withdrawal_is_checked_against_current_balance_only(ledger_conn):
    """KNOWN LIMITATION: the overdraft rule looks at the balance NOW.

    A backdated withdrawal is accepted if today's balance can cover it, even
    though it makes a PAST balance negative.
    """
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=1))
    withdraw(ledger_conn, asha.id, Money(800), occurred_at=ago(days=5))   # accepted

    assert get_balance(ledger_conn, asha.id) == Money(200)
    assert get_balance_as_of(ledger_conn, asha.id, ago(days=4)) == Money(-800)