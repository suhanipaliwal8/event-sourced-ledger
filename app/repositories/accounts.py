from uuid import UUID, uuid4

import psycopg

from app.domain.account import Account, external_account_id, fx_clearing_account_id


def create_account(
    conn: psycopg.Connection,
    name: str,
    *,
    kind: str = "CUSTOMER",
    currency: str = "INR",
    allow_negative: bool = False,
) -> Account:
    account_id = uuid4()
    conn.execute(
        "INSERT INTO accounts (id, name, kind, currency, allow_negative) "
        "VALUES (%s, %s, %s, %s, %s)",
        (account_id, name, kind, currency, allow_negative),
    )
    return Account(account_id, name, kind, currency, allow_negative)


def get_account(conn: psycopg.Connection, account_id: UUID) -> Account | None:
    row = conn.execute(
        "SELECT id, name, kind, currency, allow_negative FROM accounts WHERE id = %s",
        (account_id,),
    ).fetchone()
    if row is None:
        return None
    return Account(*row)

def lock_account(conn: psycopg.Connection, account_id: UUID) -> None:
    """Take a row lock on the account until the current transaction ends.

    Any other transaction that tries to lock the same account WAITS here.
    Must be called inside a transaction (it is released on COMMIT or ROLLBACK).
    """
    conn.execute("SELECT 1 FROM accounts WHERE id = %s FOR UPDATE", (account_id,))

def get_or_create_fx_clearing_account(conn: psycopg.Connection, currency: str) -> Account:
    """Return this currency's FX clearing account, creating it on first use.

    The id is DETERMINISTIC (see app.domain.account.fx_clearing_account_id), so
    concurrent first-time callers for the same currency race harmlessly:
    ON CONFLICT (id) DO NOTHING means at most one INSERT wins, and everyone then
    reads the same, single row.
    """
    account_id = fx_clearing_account_id(currency)
    conn.execute(
        "INSERT INTO accounts (id, name, kind, currency, allow_negative) "
        "VALUES (%s, %s, 'SYSTEM', %s, TRUE) "
        "ON CONFLICT (id) DO NOTHING",
        (account_id, f"FX_CLEARING_{currency}", currency),
    )
    account = get_account(conn, account_id)
    assert account is not None   # the row above guarantees it now exists
    return account

def get_or_create_external_account(conn: psycopg.Connection, currency: str) -> Account:
    """Return the 'outside world' account for this currency, creating it on
    first use (except INR, which already exists from Phase 3's seed migration).
    """
    account_id = external_account_id(currency)
    if currency != "INR":
        conn.execute(
            "INSERT INTO accounts (id, name, kind, currency, allow_negative) "
            "VALUES (%s, %s, 'SYSTEM', %s, TRUE) "
            "ON CONFLICT (id) DO NOTHING",
            (account_id, f"EXTERNAL_{currency}", currency),
        )
    account = get_account(conn, account_id)
    assert account is not None
    return account