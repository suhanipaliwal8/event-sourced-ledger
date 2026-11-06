from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import InvalidTransactionError
from app.domain.money import Money


@dataclass(frozen=True)
class Entry:
    """One immutable line of the ledger.

    money > 0: money flows INTO the account.
    money < 0: money flows OUT of the account.
    """

    account_id: UUID
    money: Money

    def __post_init__(self) -> None:
        if self.money.is_zero():
            raise InvalidTransactionError("an entry amount cannot be zero")