from uuid import UUID

import psycopg

from app.domain.transaction import Transaction
from app.domain.entry import Entry
from app.domain.money import Money


def insert_transaction(conn: psycopg.Connection, tx: Transaction) -> None:
    conn.execute(
        "INSERT INTO transactions (id, description, idempotency_key, occurred_at) "
        "VALUES (%s, %s, %s, %s)",
        (tx.id, tx.description, tx.idempotency_key, tx.occurred_at),
    )


def get_account_state(conn: psycopg.Connection, account_id: UUID) -> tuple[int, int]:
    """Return (balance, last_version) for an account.

    Uses the latest snapshot as a starting point, if one exists, and folds in
    only the entries recorded after it. Both the snapshot lookup and the entries
    query happen in the same call, but balance and last_version always come from
    data consistent with each other (see the docstring on why that matters:
    Phase 4's "one consistent read" requirement is preserved).
    """
    snapshot = get_latest_snapshot(conn, account_id)
    since_version = snapshot[0] if snapshot else 0
    base_balance = snapshot[1] if snapshot else 0

    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0), COALESCE(MAX(account_version), %s) "
        "FROM entries WHERE account_id = %s AND account_version > %s",
        (since_version, account_id, since_version),
    ).fetchone()
    delta, last_version = int(row[0]), int(row[1])
    return base_balance + delta, last_version


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

def get_balance_at(
    conn: psycopg.Connection,
    account_id: UUID,
    as_of,
    known_at=None,
) -> int:
    """Balance of an account using only entries that had occurred by `as_of`.

    If `known_at` is given, also only entries our ledger had RECORDED by then
    ("what did the books say at that moment?").
    Both bounds are inclusive. Datetimes must be timezone-aware.
    """
    sql = (
        "SELECT COALESCE(SUM(e.amount), 0) "
        "FROM entries e JOIN transactions t ON t.id = e.transaction_id "
        "WHERE e.account_id = %s AND t.occurred_at <= %s"
    )
    params = [account_id, as_of]
    if known_at is not None:
        sql += " AND t.recorded_at <= %s"
        params.append(known_at)
    row = conn.execute(sql, params).fetchone()
    return int(row[0])

def find_transaction_by_idempotency_key(
    conn: psycopg.Connection, key: str
) -> Transaction | None:
    """Rebuild the stored Transaction that was posted with this idempotency key."""
    row = conn.execute(
        "SELECT id, description, occurred_at FROM transactions WHERE idempotency_key = %s",
        (key,),
    ).fetchone()
    if row is None:
        return None

    entry_rows = conn.execute(
        "SELECT e.account_id, e.amount, a.currency "
        "FROM entries e JOIN accounts a ON a.id = e.account_id "
        "WHERE e.transaction_id = %s ORDER BY e.id",
        (row[0],),
    ).fetchall()

    return Transaction(
        description=row[1],
        entries=tuple(
            Entry(account_id, Money(amount, currency.strip()))
            for account_id, amount, currency in entry_rows
        ),
        id=row[0],
        occurred_at=row[2],
        idempotency_key=key,
    )

def get_latest_snapshot(
    conn: psycopg.Connection, account_id: UUID
) -> tuple[int, int] | None:
    """Return (account_version, balance) of the account's snapshot, or None."""
    row = conn.execute(
        "SELECT account_version, balance FROM balance_snapshots WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    return (row[0], row[1]) if row is not None else None


def save_snapshot(
    conn: psycopg.Connection, account_id: UUID, account_version: int, balance: int
) -> None:
    """Upsert: keep only the LATEST snapshot per account."""
    conn.execute(
        """
        INSERT INTO balance_snapshots (account_id, account_version, balance, created_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (account_id)
        DO UPDATE SET account_version = EXCLUDED.account_version,
                      balance = EXCLUDED.balance,
                      created_at = EXCLUDED.created_at
        """,
        (account_id, account_version, balance),
    )