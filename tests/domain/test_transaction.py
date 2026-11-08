import dataclasses
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.entry import Entry
from app.domain.errors import (
    InvalidTransactionError,
    UnbalancedTransactionError,
)
from app.domain.money import Money
from app.domain.transaction import Transaction

A = uuid4()
B = uuid4()
C = uuid4()


def test_balanced_transaction_is_valid():
    tx = Transaction(
        description="lunch",
        entries=(Entry(A, Money(-500)), Entry(B, Money(500))),
    )
    assert len(tx.entries) == 2


def test_transaction_with_fee_split_is_valid():
    # 3 entries: A pays 1000, B gets 900, C (bank fee) gets 100
    tx = Transaction(
        description="transfer with fee",
        entries=(
            Entry(A, Money(-1000)),
            Entry(B, Money(900)),
            Entry(C, Money(100)),
        ),
    )
    assert len(tx.entries) == 3


def test_unbalanced_transaction_is_rejected():
    with pytest.raises(UnbalancedTransactionError):
        Transaction(
            description="broken",
            entries=(Entry(A, Money(-500)), Entry(B, Money(400))),
        )


def test_single_entry_is_rejected():
    with pytest.raises(InvalidTransactionError):
        Transaction(description="one sided", entries=(Entry(A, Money(0 + 1)),))


def test_zero_amount_entry_is_rejected():
    with pytest.raises(InvalidTransactionError):
        Entry(A, Money(0))


def test_mixed_currencies_are_rejected():
    with pytest.raises(InvalidTransactionError):
        Transaction(
            description="mixed",
            entries=(Entry(A, Money(-500, "INR")), Entry(B, Money(500, "USD"))),
        )


def test_naive_datetime_is_rejected():
    with pytest.raises(InvalidTransactionError):
        Transaction(
            description="naive time",
            entries=(Entry(A, Money(-500)), Entry(B, Money(500))),
            occurred_at=datetime(2026, 1, 1),  # no timezone
        )


def test_empty_description_is_rejected():
    with pytest.raises(InvalidTransactionError):
        Transaction(
            description="   ",
            entries=(Entry(A, Money(-500)), Entry(B, Money(500))),
        )


def test_entries_list_is_converted_to_immutable_tuple():
    tx = Transaction(
        description="list input",
        entries=[Entry(A, Money(-500)), Entry(B, Money(500))],
    )
    assert isinstance(tx.entries, tuple)


def test_transaction_is_immutable():
    tx = Transaction(
        description="x",
        entries=(Entry(A, Money(-500)), Entry(B, Money(500))),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        tx.description = "changed"


def test_transfer_factory_creates_balanced_entries():
    tx = Transaction.transfer(A, B, Money(2500), description="rent")
    amounts = {e.account_id: e.money.amount for e in tx.entries}
    assert amounts == {A: -2500, B: 2500}


def test_transfer_to_same_account_is_rejected():
    with pytest.raises(InvalidTransactionError):
        Transaction.transfer(A, A, Money(100))


@pytest.mark.parametrize("amount", [0, -100])
def test_transfer_amount_must_be_positive(amount):
    with pytest.raises(InvalidTransactionError):
        Transaction.transfer(A, B, Money(amount))


def test_occurred_at_defaults_to_utc_now():
    tx = Transaction.transfer(A, B, Money(100))
    assert tx.occurred_at.tzinfo is not None
    assert tx.occurred_at.utcoffset() == timezone.utc.utcoffset(None)

def test_transfer_accepts_explicit_occurred_at():
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tx = Transaction.transfer(A, B, Money(100), occurred_at=when)
    assert tx.occurred_at == when