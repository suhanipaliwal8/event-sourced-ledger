from dataclasses import dataclass
from uuid import UUID

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