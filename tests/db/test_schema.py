import uuid

import psycopg
import pytest


# ---------- helpers ----------
def make_account(conn, allow_negative=False) -> uuid.UUID:
    account_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO accounts (id, name, kind, currency, allow_negative) "
        "VALUES (%s, 'test account', 'CUSTOMER', 'INR', %s)",
        (account_id, allow_negative),
    )
    return account_id


def make_transaction(conn, idempotency_key=None) -> uuid.UUID:
    tx_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO transactions (id, description, idempotency_key, occurred_at) "
        "VALUES (%s, 'test', %s, now())",
        (tx_id, idempotency_key),
    )
    return tx_id


def add_entry(conn, tx_id, account_id, version, amount) -> None:
    conn.execute(
        "INSERT INTO entries (transaction_id, account_id, account_version, amount) "
        "VALUES (%s, %s, %s, %s)",
        (tx_id, account_id, version, amount),
    )


def commit_balanced_transaction(conn):
    """Commit a valid 500-paise transfer and return (tx_id, a, b)."""
    a, b = make_account(conn), make_account(conn)
    tx = make_transaction(conn)
    add_entry(conn, tx, a, 1, -500)
    add_entry(conn, tx, b, 1, 500)
    conn.commit()
    return tx, a, b


# ---------- double-entry rules ----------
def test_balanced_transaction_commits(conn):
    tx, _, _ = commit_balanced_transaction(conn)
    total = conn.execute(
        "SELECT SUM(amount) FROM entries WHERE transaction_id = %s", (tx,)
    ).fetchone()[0]
    assert total == 0


def test_unbalanced_transaction_is_rejected_at_commit(conn):
    a, b = make_account(conn), make_account(conn)
    tx = make_transaction(conn)
    add_entry(conn, tx, a, 1, -500)
    add_entry(conn, tx, b, 1, 400)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.commit()


def test_transaction_without_entries_is_rejected_at_commit(conn):
    make_transaction(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.commit()


def test_zero_amount_entry_is_rejected(conn):
    a = make_account(conn)
    tx = make_transaction(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        add_entry(conn, tx, a, 1, 0)


# ---------- append-only rules ----------
def test_update_entry_is_rejected(conn):
    tx, _, _ = commit_balanced_transaction(conn)
    with pytest.raises(psycopg.IntegrityError):
        conn.execute("UPDATE entries SET amount = 1 WHERE transaction_id = %s", (tx,))


def test_delete_entry_is_rejected(conn):
    tx, _, _ = commit_balanced_transaction(conn)
    with pytest.raises(psycopg.IntegrityError):
        conn.execute("DELETE FROM entries WHERE transaction_id = %s", (tx,))


def test_update_transaction_is_rejected(conn):
    tx, _, _ = commit_balanced_transaction(conn)
    with pytest.raises(psycopg.IntegrityError):
        conn.execute("UPDATE transactions SET description = 'x' WHERE id = %s", (tx,))


def test_truncate_entries_is_rejected(conn):
    commit_balanced_transaction(conn)
    with pytest.raises(psycopg.IntegrityError):
        conn.execute("TRUNCATE entries")


# ---------- keys and constraints ----------
def test_duplicate_account_version_is_rejected(conn):
    a = make_account(conn)
    tx = make_transaction(conn)
    add_entry(conn, tx, a, 1, -500)
    with pytest.raises(psycopg.errors.UniqueViolation):
        add_entry(conn, tx, a, 1, 500)


def test_duplicate_idempotency_key_is_rejected(conn):
    key = f"key-{uuid.uuid4()}"
    make_transaction(conn, idempotency_key=key)
    with pytest.raises(psycopg.errors.UniqueViolation):
        make_transaction(conn, idempotency_key=key)


def test_entry_for_unknown_account_is_rejected(conn):
    tx = make_transaction(conn)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        add_entry(conn, tx, uuid.uuid4(), 1, -500)