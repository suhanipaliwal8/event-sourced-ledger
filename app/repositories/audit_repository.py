from collections import defaultdict
from uuid import UUID

import psycopg

from app.domain.audit import Counterparty, HistoryEntry


def get_account_history(conn: psycopg.Connection, account_id: UUID) -> list[HistoryEntry]:
    """Every entry of an account in account_version order, with its counterparties."""
    rows = conn.execute(
        """
        SELECT e.id, e.transaction_id, e.account_version, e.amount,
               t.description, t.occurred_at, t.recorded_at
        FROM entries e
        JOIN transactions t ON t.id = e.transaction_id
        WHERE e.account_id = %s
        ORDER BY e.account_version
        """,
        (account_id,),
    ).fetchall()
    if not rows:
        return []

    # Second query: the OTHER entries of the same transactions (the counterparties).
    transaction_ids = list({row[1] for row in rows})
    other_rows = conn.execute(
        """
        SELECT e.transaction_id, e.account_id, a.name, e.amount
        FROM entries e
        JOIN accounts a ON a.id = e.account_id
        WHERE e.transaction_id = ANY(%s) AND e.account_id <> %s
        ORDER BY e.id
        """,
        (transaction_ids, account_id),
    ).fetchall()

    counterparties: dict[UUID, list[Counterparty]] = defaultdict(list)
    for transaction_id, other_account_id, name, amount in other_rows:
        counterparties[transaction_id].append(Counterparty(other_account_id, name, amount))

    return [
        HistoryEntry(
            entry_id=row[0],
            transaction_id=row[1],
            account_version=row[2],
            amount=row[3],
            description=row[4],
            occurred_at=row[5],
            recorded_at=row[6],
            counterparties=tuple(counterparties.get(row[1], ())),
        )
        for row in rows
    ]


def count_unbalanced_transactions(conn: psycopg.Connection, account_id: UUID) -> int:
    """How many transactions touching this account do NOT sum to zero (should be 0)."""
    row = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT transaction_id
            FROM entries
            WHERE transaction_id IN (
                SELECT transaction_id FROM entries WHERE account_id = %s
            )
            GROUP BY transaction_id
            HAVING SUM(amount) <> 0
        ) AS unbalanced
        """,
        (account_id,),
    ).fetchone()
    return int(row[0])