from uuid import uuid4

import pytest

from app.domain.account import EXTERNAL_ACCOUNT_ID
from app.domain.entry import Entry
from app.domain.errors import AccountNotFoundError, InsufficientFundsError
from app.domain.money import Money
from app.domain.transaction import Transaction
from app.repositories.accounts import create_account
from app.services.ledger_service import (
    deposit,
    get_balance,
    get_ledger_total,
    post_transaction,
    transfer,
    withdraw,
)


def transaction_exists(conn, tx_id) -> bool:
    return conn.execute("SELECT 1 FROM transactions WHERE id = %s", (tx_id,)).fetchone() is not None


def entry_count(conn, account_id) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM entries WHERE account_id = %s", (account_id,)
    ).fetchone()[0]


# ---------- derived balances ----------
def test_new_account_has_zero_balance(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    assert get_balance(ledger_conn, asha.id) == Money(0)


def test_balance_is_sum_of_entries(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    deposit(ledger_conn, asha.id, Money(500))
    withdraw(ledger_conn, asha.id, Money(300))
    assert get_balance(ledger_conn, asha.id) == Money(1_200, "INR")


def test_balance_equals_replay_of_history(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    deposit(ledger_conn, asha.id, Money(250))
    withdraw(ledger_conn, asha.id, Money(100))

    history = [
        row[0]
        for row in ledger_conn.execute(
            "SELECT amount FROM entries WHERE account_id = %s ORDER BY account_version",
            (asha.id,),
        )
    ]
    assert history == [1_000, 250, -100]          # the event stream
    assert sum(history) == get_balance(ledger_conn, asha.id).amount   # replayed state


def test_transfer_moves_balance_between_accounts(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(5_000))

    transfer(ledger_conn, asha.id, rahul.id, Money(2_000), "rent")

    assert get_balance(ledger_conn, asha.id) == Money(3_000)
    assert get_balance(ledger_conn, rahul.id) == Money(2_000)


def test_balance_of_unknown_account_raises(ledger_conn):
    with pytest.raises(AccountNotFoundError):
        get_balance(ledger_conn, uuid4())


def test_ledger_total_is_always_zero(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(777))
    assert get_ledger_total(ledger_conn) == 0


# ---------- overdraft rule ----------
def test_withdraw_more_than_balance_is_rejected_and_nothing_written(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))

    with pytest.raises(InsufficientFundsError):
        withdraw(ledger_conn, asha.id, Money(1_500))

    assert get_balance(ledger_conn, asha.id) == Money(1_000)
    assert entry_count(ledger_conn, asha.id) == 1      # only the original deposit


def test_withdraw_exact_balance_is_allowed(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    withdraw(ledger_conn, asha.id, Money(1_000))
    assert get_balance(ledger_conn, asha.id) == Money(0)


def test_transfer_that_overdraws_is_rejected_atomically(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(500))

    tx = Transaction.transfer(asha.id, rahul.id, Money(800))
    with pytest.raises(InsufficientFundsError):
        post_transaction(ledger_conn, tx)

    assert not transaction_exists(ledger_conn, tx.id)
    assert get_balance(ledger_conn, asha.id) == Money(500)
    assert get_balance(ledger_conn, rahul.id) == Money(0)


def test_multi_entry_overdraft_rolls_back_every_entry(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    b = create_account(ledger_conn, "B")
    c = create_account(ledger_conn, "C")
    deposit(ledger_conn, asha.id, Money(1_000))

    tx = Transaction(
        description="split payment",
        entries=(
            Entry(asha.id, Money(-1_500)),   # overdraws Asha
            Entry(b.id, Money(1_000)),
            Entry(c.id, Money(500)),
        ),
    )
    with pytest.raises(InsufficientFundsError):
        post_transaction(ledger_conn, tx)

    assert not transaction_exists(ledger_conn, tx.id)
    assert get_balance(ledger_conn, asha.id) == Money(1_000)
    assert get_balance(ledger_conn, b.id) == Money(0)
    assert get_balance(ledger_conn, c.id) == Money(0)


# ---------- SYSTEM accounts ----------
def test_system_account_may_go_negative(ledger_conn):
    vault = create_account(ledger_conn, "Bank vault", kind="SYSTEM", allow_negative=True)
    asha = create_account(ledger_conn, "Asha")

    transfer(ledger_conn, vault.id, asha.id, Money(500))

    assert get_balance(ledger_conn, vault.id) == Money(-500)
    assert get_balance(ledger_conn, asha.id) == Money(500)


def test_external_balance_moves_opposite_to_a_deposit(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    before = get_balance(ledger_conn, EXTERNAL_ACCOUNT_ID).amount

    deposit(ledger_conn, asha.id, Money(700))

    after = get_balance(ledger_conn, EXTERNAL_ACCOUNT_ID).amount
    assert after == before - 700