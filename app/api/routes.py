from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.dependencies import get_conn
from app.api.schemas import (
    AccountCreate,
    AccountOut,
    AuditOut,
    BalanceOut,
    MoneyRequest,
    TransactionOut,
    TransferRequest,
)
from app.domain.errors import AccountNotFoundError, SystemAccountNotAllowedError
from app.domain.money import Money
from app.repositories import accounts as accounts_repo
from app.services import audit_service, ledger_service

router = APIRouter()

# Annotated shortcut: "give me a database connection for this request".
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def _require_customer_account(conn: psycopg.Connection, account_id: UUID) -> None:
    """Public endpoints may only move money on CUSTOMER accounts.

    Without this, a client could transfer money OUT of the EXTERNAL account
    and effectively mint money.
    """
    account = accounts_repo.get_account(conn, account_id)
    if account is None:
        raise AccountNotFoundError(f"account {account_id} does not exist")
    if account.kind != "CUSTOMER":
        raise SystemAccountNotAllowedError(
            "system accounts cannot be used through the public API"
        )


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, conn: Conn):
    account = accounts_repo.create_account(conn, body.name, currency=body.currency)
    return AccountOut.from_domain(account)


@router.get("/accounts/{account_id}", response_model=AccountOut)
def read_account(account_id: UUID, conn: Conn):
    account = accounts_repo.get_account(conn, account_id)
    if account is None:
        raise AccountNotFoundError(f"account {account_id} does not exist")
    return AccountOut.from_domain(account)


@router.get("/accounts/{account_id}/balance", response_model=BalanceOut)
def read_balance(
    account_id: UUID,
    conn: Conn,
    as_of: Annotated[
        AwareDatetime | None,
        Query(description="Balance as of this moment (needs a timezone, e.g. ...Z)"),
    ] = None,
    known_at: Annotated[
        AwareDatetime | None,
        Query(description="Only count entries the ledger had recorded by this moment"),
    ] = None,
):
    if as_of is None and known_at is None:
        money = ledger_service.get_balance(conn, account_id)
        return BalanceOut.from_money(account_id, money)

    effective_as_of = as_of or datetime.now(timezone.utc)
    money = ledger_service.get_balance_as_of(conn, account_id, effective_as_of, known_at)
    return BalanceOut.from_money(account_id, money, effective_as_of, known_at)


@router.post(
    "/accounts/{account_id}/deposits", response_model=TransactionOut, status_code=201
)
def make_deposit(account_id: UUID, body: MoneyRequest, conn: Conn):
    _require_customer_account(conn, account_id)
    tx = ledger_service.deposit(
        conn,
        account_id,
        Money(body.amount, body.currency),
        body.description or "deposit",
        body.occurred_at,
    )
    return TransactionOut.from_domain(tx)


@router.post(
    "/accounts/{account_id}/withdrawals", response_model=TransactionOut, status_code=201
)
def make_withdrawal(account_id: UUID, body: MoneyRequest, conn: Conn):
    _require_customer_account(conn, account_id)
    tx = ledger_service.withdraw(
        conn,
        account_id,
        Money(body.amount, body.currency),
        body.description or "withdrawal",
        body.occurred_at,
    )
    return TransactionOut.from_domain(tx)


@router.post("/transfers", response_model=TransactionOut, status_code=201)
def make_transfer(body: TransferRequest, conn: Conn):
    _require_customer_account(conn, body.from_account_id)
    _require_customer_account(conn, body.to_account_id)
    tx = ledger_service.transfer(
        conn,
        body.from_account_id,
        body.to_account_id,
        Money(body.amount, body.currency),
        body.description or "transfer",
        body.occurred_at,
    )
    return TransactionOut.from_domain(tx)

@router.get("/accounts/{account_id}/audit", response_model=AuditOut)
def read_audit_trail(
    account_id: UUID,
    conn: Conn,
    after_version: Annotated[
        int, Query(ge=0, description="Return only entries after this account_version")
    ] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Page size")] = 50,
):
    report = audit_service.get_audit_trail(conn, account_id, after_version, limit)
    return AuditOut.model_validate(report)