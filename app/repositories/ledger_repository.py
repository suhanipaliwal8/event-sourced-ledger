from uuid import UUID

import psycopg

from app.domain.transaction import Transaction


def insert_transaction(conn: psycopg.Connection, tx: Transaction) -> None:
    conn.execute(
        "INSERT INTO transactions (id, description, occurred_at) VALUES (%s, %s, %s)",
        (tx.id, tx.description, tx.occurred_at),
    )


def get_last_version(conn: psycopg.Connection, account_id: UUID) -> int:
    """Latest account_version for this account, or 0 if it has no entries yet."""
    row = conn.execute(
        "SELECT COALESCE(MAX(account_version), 0) FROM entries WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    return row[0]


def insert_entry(
    conn: psycopg.Connection,
    transaction_id: UUID,
    account_id: UUID,
    account_version: int,
    amount: int,
) -> None:
    conn.execute(
        "INSERT INTO entries (transaction_id, account_id, account_version, amount) "
        "VALUES (%s, %s, %s, %s)",
        (transaction_id, account_id, account_version, amount),
    )