from dataclasses import dataclass
from uuid import UUID
import uuid as _uuid

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

# Fixed namespace for deriving FX clearing account ids deterministically from
# a currency code, the same way EXTERNAL_ACCOUNT_ID is a fixed, known id.
_FX_CLEARING_NAMESPACE = _uuid.UUID("00000000-0000-0000-0000-00000000fec0")


def fx_clearing_account_id(currency: str) -> UUID:
    """The fixed, deterministic account id for a currency's FX clearing account.

    Same currency always maps to the same id, so it can be looked up or
    created without a prior directory of "which currencies exist".
    """
    return _uuid.uuid5(_FX_CLEARING_NAMESPACE, currency)

_EXTERNAL_NAMESPACE = _uuid.UUID("00000000-0000-0000-0000-00000000ec00")


def external_account_id(currency: str) -> UUID:
    """The id of the 'outside world' account for a given currency.

    INR keeps using the original, already-seeded EXTERNAL_ACCOUNT_ID (Phase 3),
    so every pre-existing deposit/withdrawal and test is unaffected. Any other
    currency gets its own deterministic id, created lazily like an FX clearing
    account.
    """
    if currency == "INR":
        return EXTERNAL_ACCOUNT_ID
    return _uuid.uuid5(_EXTERNAL_NAMESPACE, currency)