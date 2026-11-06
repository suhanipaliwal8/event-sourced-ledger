from uuid import UUID, uuid4

import psycopg

from app.domain.account import Account


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