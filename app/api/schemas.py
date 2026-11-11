from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict ,Field, StringConstraints

from app.domain.account import Account
from app.domain.money import Money
from app.domain.transaction import Transaction

# strict=True: JSON 10.5 or "10" is REJECTED instead of silently converted.
Amount = Annotated[
    int,
    Field(strict=True, gt=0, description="Amount in minor units (paise/cents)"),
]
CurrencyCode = Annotated[
    str,
    Field(pattern=r"^[A-Z]{3}$", description="3-letter uppercase code, e.g. INR"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


# ---------- requests ----------
class AccountCreate(BaseModel):
    name: Name
    currency: CurrencyCode = "INR"


class MoneyRequest(BaseModel):
    """Body for deposits and withdrawals (and the base of transfers)."""

    amount: Amount
    currency: CurrencyCode
    description: str | None = Field(default=None, max_length=200)
    # Optional backdating. Must include a timezone (e.g. 2026-11-03T10:00:00Z)
    # and must not be in the future.
    occurred_at: AwareDatetime | None = None


class TransferRequest(MoneyRequest):
    from_account_id: UUID
    to_account_id: UUID


# ---------- responses ----------
class AccountOut(BaseModel):
    id: UUID
    name: str
    kind: str
    currency: str
    allow_negative: bool

    @classmethod
    def from_domain(cls, account: Account) -> "AccountOut":
        return cls(
            id=account.id,
            name=account.name,
            kind=account.kind,
            currency=account.currency,
            allow_negative=account.allow_negative,
        )


class EntryOut(BaseModel):
    account_id: UUID
    amount: int
    currency: str


class TransactionOut(BaseModel):
    id: UUID
    description: str
    occurred_at: datetime
    entries: list[EntryOut]

    @classmethod
    def from_domain(cls, tx: Transaction) -> "TransactionOut":
        return cls(
            id=tx.id,
            description=tx.description,
            occurred_at=tx.occurred_at,
            entries=[
                EntryOut(
                    account_id=e.account_id,
                    amount=e.money.amount,
                    currency=e.money.currency,
                )
                for e in tx.entries
            ],
        )


class BalanceOut(BaseModel):
    account_id: UUID
    amount: int
    currency: str
    as_of: datetime | None = None      # set only for point-in-time queries
    known_at: datetime | None = None

    @classmethod
    def from_money(
        cls,
        account_id: UUID,
        money: Money,
        as_of: datetime | None = None,
        known_at: datetime | None = None,
    ) -> "BalanceOut":
        return cls(
            account_id=account_id,
            amount=money.amount,
            currency=money.currency,
            as_of=as_of,
            known_at=known_at,
        )

# ---------- audit trail ----------
class FromDomain(BaseModel):
    """Base for responses built straight from domain objects (read their attributes)."""

    model_config = ConfigDict(from_attributes=True)


class CounterpartyOut(FromDomain):
    account_id: UUID
    account_name: str
    amount: int


class AuditLineOut(FromDomain):
    account_version: int
    entry_id: int
    transaction_id: UUID
    description: str
    amount: int
    running_balance: int
    occurred_at: datetime
    recorded_at: datetime
    counterparties: list[CounterpartyOut]
    explanation: str


class AuditSummaryOut(FromDomain):
    entry_count: int
    total_credits: int
    total_debits: int
    opening_balance: int
    closing_balance: int


class AuditIntegrityOut(FromDomain):
    ok: bool
    balance_matches: bool
    versions_contiguous: bool
    unbalanced_transactions: int


class AuditOut(FromDomain):
    account_id: UUID
    currency: str
    summary: AuditSummaryOut
    integrity: AuditIntegrityOut
    lines: list[AuditLineOut]
    next_after_version: int | None

# ---------- fx transfer ----------
class FxTransferRequest(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    send_amount: Amount
    send_currency: CurrencyCode
    receive_amount: Amount
    receive_currency: CurrencyCode
    description: str | None = Field(default=None, max_length=200)
    occurred_at: AwareDatetime | None = None