from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import InsufficientFundsError

# Fixed id of the SYSTEM account that represents "the outside world".
# Deposits come FROM it and withdrawals go TO it. It is allowed to go negative.
EXTERNAL_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class Account:
    id: UUID
    name: str
    kind: str  # 'CUSTOMER' or 'SYSTEM'
    currency: str
    allow_negative: bool

    def new_balance_after(self, current_balance: int, delta: int) -> int:
        """Return the balance after applying `delta`, or raise if it overdraws.

        Only a debit (delta < 0) can overdraw. Credits are always allowed.
        """
        new_balance = current_balance + delta
        if delta < 0 and new_balance < 0 and not self.allow_negative:
            raise InsufficientFundsError(
                f"account {self.id} would go to {new_balance}; overdraft is not allowed"
            )
        return new_balance