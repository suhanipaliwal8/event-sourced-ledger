from app.repositories.accounts import create_account
from app.repositories.ledger_repository import (
    get_account_state,
    get_latest_snapshot,
    save_snapshot,
)
from app.domain.money import Money
from app.services.ledger_service import deposit, withdraw


def test_no_snapshot_returns_none(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    assert get_latest_snapshot(ledger_conn, asha.id) is None


def test_save_and_read_snapshot(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    save_snapshot(ledger_conn, asha.id, 5, 10_000)
    assert get_latest_snapshot(ledger_conn, asha.id) == (5, 10_000)


def test_saving_again_replaces_the_previous_snapshot(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    save_snapshot(ledger_conn, asha.id, 5, 10_000)
    save_snapshot(ledger_conn, asha.id, 9, 17_000)
    assert get_latest_snapshot(ledger_conn, asha.id) == (9, 17_000)


def test_account_state_without_a_snapshot_replays_everything(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    deposit(ledger_conn, asha.id, Money(500))
    assert get_account_state(ledger_conn, asha.id) == (1_500, 2)


def test_account_state_with_a_snapshot_folds_in_only_newer_entries(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))     # version 1
    deposit(ledger_conn, asha.id, Money(500))       # version 2
    save_snapshot(ledger_conn, asha.id, 2, 1_500)   # pretend we snapshotted here
    withdraw(ledger_conn, asha.id, Money(200))      # version 3, AFTER the snapshot

    assert get_account_state(ledger_conn, asha.id) == (1_300, 3)


def test_account_state_with_a_snapshot_and_no_new_entries(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(700))
    save_snapshot(ledger_conn, asha.id, 1, 700)

    assert get_account_state(ledger_conn, asha.id) == (700, 1)