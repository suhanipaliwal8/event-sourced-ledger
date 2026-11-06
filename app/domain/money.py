from dataclasses import dataclass

from app.domain.errors import InvalidMoneyError


@dataclass(frozen=True)
class Money:
    """An exact amount in minor units (paise for INR, cents for USD).

    amount is a signed integer: 500 INR means Rs 5.00.
    """

    amount: int
    currency: str = "INR"

    def __post_init__(self) -> None:
        # bool is a subclass of int in Python, so check it explicitly.
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise InvalidMoneyError(
                "amount must be an integer in minor units (e.g. paise), not a float"
            )
        if not (
            isinstance(self.currency, str)
            and len(self.currency) == 3
            and self.currency.isalpha()
            and self.currency.isupper()
        ):
            raise InvalidMoneyError(
                "currency must be a 3-letter uppercase code like 'INR'"
            )

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise InvalidMoneyError("cannot add money of different currencies")
        return Money(self.amount + other.amount, self.currency)

    def is_zero(self) -> bool:
        return self.amount == 0