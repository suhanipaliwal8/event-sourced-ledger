import dataclasses

import pytest

from app.domain.errors import InvalidMoneyError
from app.domain.money import Money


def test_money_holds_integer_paise():
    m = Money(500)
    assert m.amount == 500
    assert m.currency == "INR"


def test_float_amount_is_rejected():
    with pytest.raises(InvalidMoneyError):
        Money(10.5)


def test_bool_amount_is_rejected():
    # In Python, True is an int. We must not accept it as money.
    with pytest.raises(InvalidMoneyError):
        Money(True)


@pytest.mark.parametrize("bad", ["inr", "INRR", "IN", "12A", ""])
def test_bad_currency_is_rejected(bad):
    with pytest.raises(InvalidMoneyError):
        Money(100, bad)


def test_negation():
    assert -Money(500) == Money(-500)


def test_addition_same_currency():
    assert Money(300) + Money(200) == Money(500)


def test_addition_different_currency_is_rejected():
    with pytest.raises(InvalidMoneyError):
        Money(100, "INR") + Money(100, "USD")


def test_money_is_immutable():
    m = Money(100)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.amount = 999