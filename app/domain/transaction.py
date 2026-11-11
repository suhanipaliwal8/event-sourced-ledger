from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.entry import Entry
from app.domain.errors import InvalidTransactionError, UnbalancedTransactionError
from app.domain.money import Money

MAX_IDEMPOTENCY_KEY_LENGTH = 255


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Transaction:
    """A group of entries that together obey double-entry bookkeeping.

    Invariants (checked on creation, so an invalid Transaction cannot exist):
      1. at least 2 entries
      2. entries sum to exactly zero WITHIN EACH CURRENCY (a single-currency
         transaction is the special case of one currency group; cross-currency
         transfers add FX clearing entries so each currency group still balances)
      3. occurred_at is timezone-aware
      4. entry amounts are never zero (enforced by Entry itself)
      5. an idempotency key, if present, is 1 to 255 characters and not blank
    """

    description: str
    entries: tuple[Entry, ...]
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utc_now)
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        # If someone passed a list, freeze it into a tuple.
        object.__setattr__(self, "entries", tuple(self.entries))

        if not self.description.strip():
            raise InvalidTransactionError("description cannot be empty")
        if len(self.entries) < 2:
            raise InvalidTransactionError("a transaction needs at least 2 entries")
        if self.occurred_at.tzinfo is None:
            raise InvalidTransactionError("occurred_at must be timezone-aware")
        if self.idempotency_key is not None and (
            not self.idempotency_key.strip()
            or len(self.idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH
        ):
            raise InvalidTransactionError(
                f"idempotency key must be 1 to {MAX_IDEMPOTENCY_KEY_LENGTH} characters and not blank"
            )

        totals_by_currency: dict[str, int] = defaultdict(int)
        for e in self.entries:
            totals_by_currency[e.money.currency] += e.money.amount
        for currency, total in totals_by_currency.items():
            if total != 0:
                raise UnbalancedTransactionError(
                    f"entries in {currency} must sum to zero, but sum to {total}"
                )

    def same_request_as(self, other: "Transaction") -> bool:
        """True if both describe the same request: same accounts, signed amounts,
        currency and description. The id and occurred_at are deliberately ignored,
        because every retry creates a new id and a new 'now'."""

        def signature(tx: "Transaction"):
            return (
                tx.description,
                sorted((str(e.account_id), e.money.amount, e.money.currency) for e in tx.entries),
            )

        return signature(self) == signature(other)

    @classmethod
    def transfer(
        cls,
        from_account: UUID,
        to_account: UUID,
        money: Money,
        description: str = "transfer",
        occurred_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> "Transaction":
        """Convenience builder: move `money` from one account to another, SAME currency."""
        if from_account == to_account:
            raise InvalidTransactionError("cannot transfer to the same account")
        if money.amount <= 0:
            raise InvalidTransactionError("transfer amount must be positive")
        return cls(
            description=description,
            entries=(Entry(from_account, -money), Entry(to_account, money)),
            occurred_at=occurred_at or _utc_now(),
            idempotency_key=idempotency_key,
        )