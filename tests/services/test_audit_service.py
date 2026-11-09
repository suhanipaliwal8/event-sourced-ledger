from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.errors import AccountNotFoundError
from app.domain.money import Money
from app.repositories.accounts import create_account
from app.services import audit_service
from app.services.audit_service import get_audit_trail
from app.services.ledger_service import deposit, get_balance, transfer


def ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def test_audit_of_account_without_history(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    report = get_audit_trail(ledger_conn, asha.id)

    assert report.lines == ()
    assert report.summary.closing_balance == 0
    assert report.integrity.ok
    assert report.next_after_version is None


def test_audit_explains_how_the_balance_was_reached(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(1_000))
    transfer(ledger_conn, asha.id, rahul.id, Money(300), "rent")
    deposit(ledger_conn, asha.id, Money(200))

    report = get_audit_trail(ledger_conn, asha.id)

    assert [line.running_balance for line in report.lines] == [1_000, 700, 900]
    assert report.lines[0].counterparties[0].account_name == "EXTERNAL"
    assert report.lines[1].counterparties[0].account_name == "Rahul"
    assert report.lines[1].explanation == "Sent 300 to Rahul (rent)"
    assert report.summary.closing_balance == get_balance(ledger_conn, asha.id).amount


def test_integrity_is_ok_for_a_normal_history(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(500))
    transfer(ledger_conn, asha.id, rahul.id, Money(200))

    report = get_audit_trail(ledger_conn, asha.id)
    assert report.integrity.balance_matches
    assert report.integrity.versions_contiguous
    assert report.integrity.unbalanced_transactions == 0
    assert report.integrity.ok


def test_audit_shows_both_times_of_a_backdated_entry(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    when = ago(days=5)
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=when)

    line = get_audit_trail(ledger_conn, asha.id).lines[0]
    assert line.occurred_at == when
    assert line.recorded_at > line.occurred_at       # we learned about it later


def test_audit_replays_in_recorded_order_not_occurred_order(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000), occurred_at=ago(days=1))   # recorded first
    deposit(ledger_conn, asha.id, Money(500), occurred_at=ago(days=5))     # recorded second, older

    lines = get_audit_trail(ledger_conn, asha.id).lines
    assert [line.account_version for line in lines] == [1, 2]
    assert [line.running_balance for line in lines] == [1_000, 1_500]
    assert lines[1].occurred_at < lines[0].occurred_at


def test_pagination_keeps_running_balances_correct(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    for _ in range(5):
        deposit(ledger_conn, asha.id, Money(100))

    page1 = get_audit_trail(ledger_conn, asha.id, after_version=0, limit=2)
    assert [line.account_version for line in page1.lines] == [1, 2]
    assert page1.next_after_version == 2

    page2 = get_audit_trail(ledger_conn, asha.id, after_version=2, limit=2)
    assert [line.account_version for line in page2.lines] == [3, 4]
    assert [line.running_balance for line in page2.lines] == [300, 400]
    assert page2.next_after_version == 4

    page3 = get_audit_trail(ledger_conn, asha.id, after_version=4, limit=2)
    assert [line.account_version for line in page3.lines] == [5]
    assert page3.next_after_version is None
    assert page3.summary.entry_count == 5        # summary always covers the full history


def test_unknown_account_raises(ledger_conn):
    with pytest.raises(AccountNotFoundError):
        get_audit_trail(ledger_conn, uuid4())


def test_balance_mismatch_is_detected(ledger_conn, monkeypatch):
    """The DB makes a real mismatch impossible, so we inject a wrong balance."""
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))

    monkeypatch.setattr(
        audit_service, "get_account_state", lambda conn, account_id: (999_999, 1)
    )

    report = get_audit_trail(ledger_conn, asha.id)
    assert report.integrity.balance_matches is False
    assert report.integrity.ok is False