from uuid import uuid4

import pytest

from app.domain.errors import IdempotencyKeyReusedError, InsufficientFundsError
from app.domain.money import Money
from app.repositories.accounts import create_account
from app.services.ledger_service import deposit, get_balance, withdraw
from tests.helpers import run_concurrently


def new_key() -> str:
    return f"key-{uuid4()}"


def transactions_with_key(conn, key) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE idempotency_key = %s", (key,)
    ).fetchone()[0]


def test_same_key_posts_only_once(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    key = new_key()

    first = deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=key)
    second = deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=key)

    assert second.id == first.id
    assert get_balance(ledger_conn, asha.id) == Money(1_000)    # not 2,000
    assert transactions_with_key(ledger_conn, key) == 1


def test_replay_returns_the_original_entries(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    key = new_key()

    first = deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=key)
    second = deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=key)

    assert second.entries == first.entries
    assert second.occurred_at == first.occurred_at
    assert second.description == first.description


def test_same_key_with_different_amount_is_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    key = new_key()
    deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=key)

    with pytest.raises(IdempotencyKeyReusedError):
        deposit(ledger_conn, asha.id, Money(2_000), idempotency_key=key)

    assert get_balance(ledger_conn, asha.id) == Money(1_000)


def test_same_key_for_a_different_account_is_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    key = new_key()
    deposit(ledger_conn, asha.id, Money(100), idempotency_key=key)

    with pytest.raises(IdempotencyKeyReusedError):
        deposit(ledger_conn, rahul.id, Money(100), idempotency_key=key)

    assert get_balance(ledger_conn, rahul.id) == Money(0)


def test_different_keys_post_separately(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=new_key())
    deposit(ledger_conn, asha.id, Money(1_000), idempotency_key=new_key())
    assert get_balance(ledger_conn, asha.id) == Money(2_000)


def test_without_a_key_nothing_is_deduplicated(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    deposit(ledger_conn, asha.id, Money(1_000))
    assert get_balance(ledger_conn, asha.id) == Money(2_000)


def test_replay_works_even_after_the_balance_is_used_up(ledger_conn):
    """A replay must return the original result, not fail the overdraft check."""
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    key = new_key()

    first = withdraw(ledger_conn, asha.id, Money(1_000), idempotency_key=key)
    second = withdraw(ledger_conn, asha.id, Money(1_000), idempotency_key=key)   # balance is 0 now

    assert second.id == first.id
    assert get_balance(ledger_conn, asha.id) == Money(0)


def test_a_failed_request_does_not_burn_the_key(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    key = new_key()

    with pytest.raises(InsufficientFundsError):
        withdraw(ledger_conn, asha.id, Money(5_000), idempotency_key=key)
    assert transactions_with_key(ledger_conn, key) == 0

    deposit(ledger_conn, asha.id, Money(6_000))
    withdraw(ledger_conn, asha.id, Money(5_000), idempotency_key=key)    # same key, now fine

    assert get_balance(ledger_conn, asha.id) == Money(1_000)
    assert transactions_with_key(ledger_conn, key) == 1


def test_concurrent_requests_with_the_same_key_post_once(db_url, ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    key = new_key()
    seen_ids = []

    outcomes = run_concurrently(
        db_url,
        [lambda c: seen_ids.append(deposit(c, asha.id, Money(500), idempotency_key=key).id)] * 10,
    )

    assert all(o is None for o in outcomes)          # every request got an answer
    assert len(set(seen_ids)) == 1                   # ...and it was the same transaction
    assert get_balance(ledger_conn, asha.id) == Money(500)
    assert transactions_with_key(ledger_conn, key) == 1