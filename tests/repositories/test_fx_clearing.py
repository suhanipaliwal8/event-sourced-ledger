from app.domain.account import fx_clearing_account_id
from app.repositories.accounts import get_or_create_fx_clearing_account
from tests.helpers import run_concurrently


def test_creates_the_clearing_account_on_first_use(ledger_conn):
    account = get_or_create_fx_clearing_account(ledger_conn, "USD")
    assert account.id == fx_clearing_account_id("USD")
    assert account.kind == "SYSTEM"
    assert account.allow_negative is True
    assert account.currency == "USD"


def test_second_call_returns_the_same_account(ledger_conn):
    first = get_or_create_fx_clearing_account(ledger_conn, "USD")
    second = get_or_create_fx_clearing_account(ledger_conn, "USD")
    assert first == second


def test_concurrent_first_use_is_safe(db_url):
    outcomes = run_concurrently(
        db_url, [lambda c: get_or_create_fx_clearing_account(c, "GBP")] * 10
    )
    assert all(o is None for o in outcomes)