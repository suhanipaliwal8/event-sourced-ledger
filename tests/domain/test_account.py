from uuid import uuid4

import pytest

from app.domain.account import Account
from app.domain.errors import InsufficientFundsError


def make_account(allow_negative: bool) -> Account:
    return Account(uuid4(), "test", "CUSTOMER", "INR", allow_negative)


def test_customer_cannot_overdraw():
    with pytest.raises(InsufficientFundsError):
        make_account(False).new_balance_after(1_000, -1_500)


def test_customer_can_withdraw_down_to_exactly_zero():
    assert make_account(False).new_balance_after(1_000, -1_000) == 0


def test_system_account_may_go_negative():
    assert make_account(True).new_balance_after(0, -500) == -500


def test_credit_is_always_allowed():
    assert make_account(False).new_balance_after(0, 500) == 500