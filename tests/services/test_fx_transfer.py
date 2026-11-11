import pytest

from app.domain.errors import AccountNotFoundError, InsufficientFundsError, InvalidTransactionError
from app.domain.money import Money
from app.repositories.accounts import create_account
from app.services.audit_service import get_audit_trail
from app.services.ledger_service import (
    deposit,
    fx_transfer,
    get_balance,
    get_ledger_totals_by_currency,
)


def test_fx_transfer_moves_money_at_the_implied_rate(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    deposit(ledger_conn, asha.id, Money(10_000, "USD"))   # $100.00

    fx_transfer(ledger_conn, asha.id, Money(10_000, "USD"), rahul.id, Money(830_000, "INR"))

    assert get_balance(ledger_conn, asha.id) == Money(0, "USD")
    assert get_balance(ledger_conn, rahul.id) == Money(830_000, "INR")


def test_fx_clearing_accounts_absorb_the_difference(ledger_conn):
    from app.domain.account import fx_clearing_account_id

    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    deposit(ledger_conn, asha.id, Money(10_000, "USD"))

    fx_transfer(ledger_conn, asha.id, Money(10_000, "USD"), rahul.id, Money(830_000, "INR"))

    usd_clearing = get_balance(ledger_conn, fx_clearing_account_id("USD"))
    inr_clearing = get_balance(ledger_conn, fx_clearing_account_id("INR"))
    assert usd_clearing == Money(10_000, "USD")
    assert inr_clearing == Money(-830_000, "INR")


def test_every_currency_is_conserved_across_the_whole_ledger(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    deposit(ledger_conn, asha.id, Money(5_000, "USD"))
    fx_transfer(ledger_conn, asha.id, Money(5_000, "USD"), rahul.id, Money(415_000, "INR"))

    totals = get_ledger_totals_by_currency(ledger_conn)
    assert totals["USD"] == 0
    assert totals["INR"] == 0


def test_fx_transfer_respects_the_overdraft_rule(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    deposit(ledger_conn, asha.id, Money(100, "USD"))

    with pytest.raises(InsufficientFundsError):
        fx_transfer(ledger_conn, asha.id, Money(10_000, "USD"), rahul.id, Money(830_000, "INR"))

    assert get_balance(ledger_conn, asha.id) == Money(100, "USD")


def test_same_currency_fx_transfer_is_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="USD")
    deposit(ledger_conn, asha.id, Money(100, "USD"))

    with pytest.raises(InvalidTransactionError):
        fx_transfer(ledger_conn, asha.id, Money(100, "USD"), rahul.id, Money(100, "USD"))


def test_non_positive_amounts_are_rejected(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    with pytest.raises(InvalidTransactionError):
        fx_transfer(ledger_conn, asha.id, Money(0, "USD"), rahul.id, Money(100, "INR"))


def test_unknown_account_raises(ledger_conn):
    import uuid

    asha = create_account(ledger_conn, "Asha", currency="USD")
    with pytest.raises(AccountNotFoundError):
        fx_transfer(ledger_conn, asha.id, Money(100, "USD"), uuid.uuid4(), Money(8_300, "INR"))


def test_audit_integrity_is_ok_after_fx_activity(ledger_conn):
    asha = create_account(ledger_conn, "Asha", currency="USD")
    rahul = create_account(ledger_conn, "Rahul", currency="INR")
    deposit(ledger_conn, asha.id, Money(10_000, "USD"))
    fx_transfer(ledger_conn, asha.id, Money(10_000, "USD"), rahul.id, Money(830_000, "INR"))

    assert get_audit_trail(ledger_conn, asha.id).integrity.ok
    assert get_audit_trail(ledger_conn, rahul.id).integrity.ok