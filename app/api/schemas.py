from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

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
    """Body for deposits and withdrawals."""

    amount: Amount
    currency: CurrencyCode
    description: str | None = Field(default=None, max_length=200)


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

    @classmethod
    def from_money(cls, account_id: UUID, money: Money) -> "BalanceOut":
        return cls(account_id=account_id, amount=money.amount, currency=money.currency)