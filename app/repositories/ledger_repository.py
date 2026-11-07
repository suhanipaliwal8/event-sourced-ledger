from uuid import UUID

import psycopg

from app.domain.transaction import Transaction


def insert_transaction(conn: psycopg.Connection, tx: Transaction) -> None:
    conn.execute(
        "INSERT INTO transactions (id, description, occurred_at) VALUES (%s, %s, %s)",
        (tx.id, tx.description, tx.occurred_at),
    )


def get_account_state(conn: psycopg.Connection, account_id: UUID) -> tuple[int, int]:
    """Return (balance, last_version) for an account.

    Both values are read in ONE statement, so they always belong to the same
    snapshot of the data. Reading them separately could pair a stale balance
    with a fresh version and let an overdraft slip through.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0), COALESCE(MAX(account_version), 0) "
        "FROM entries WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    # SUM() of bigint comes back as Decimal from Postgres, so convert to int.
    return int(row[0]), int(row[1])


def get_ledger_total(conn: psycopg.Connection) -> int:
    """Sum of ALL entries in the ledger. In a correct double-entry ledger this is 0."""
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM entries").fetchone()
    return int(row[0])


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