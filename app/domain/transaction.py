from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.entry import Entry
from app.domain.errors import InvalidTransactionError, UnbalancedTransactionError
from app.domain.money import Money


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Transaction:
    """A group of entries that together obey double-entry bookkeeping.

    Invariants (checked on creation, so an invalid Transaction cannot exist):
      1. at least 2 entries
      2. all entries use the same currency (multi-currency comes in Phase 11)
      3. entries sum to exactly zero
      4. occurred_at is timezone-aware
    """

    description: str
    entries: tuple[Entry, ...]
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        # If someone passed a list, freeze it into a tuple.
        # (object.__setattr__ is needed because the dataclass is frozen.)
        object.__setattr__(self, "entries", tuple(self.entries))

        if not self.description.strip():
            raise InvalidTransactionError("description cannot be empty")
        if len(self.entries) < 2:
            raise InvalidTransactionError("a transaction needs at least 2 entries")
        if self.occurred_at.tzinfo is None:
            raise InvalidTransactionError("occurred_at must be timezone-aware")

        currencies = {e.money.currency for e in self.entries}
        if len(currencies) != 1:
            raise InvalidTransactionError(
                "all entries must use the same currency (for now)"
            )

        total = sum(e.money.amount for e in self.entries)
        if total != 0:
            raise UnbalancedTransactionError(
                f"entries must sum to zero, but sum to {total}"
            )

    @classmethod
    def transfer(
        cls,
        from_account: UUID,
        to_account: UUID,
        money: Money,
        description: str = "transfer",
    ) -> "Transaction":
        """Convenience builder: move `money` from one account to another."""
        if from_account == to_account:
            raise InvalidTransactionError("cannot transfer to the same account")
        if money.amount <= 0:
            raise InvalidTransactionError("transfer amount must be positive")
        return cls(
            description=description,
            entries=(Entry(from_account, -money), Entry(to_account, money)),
        )