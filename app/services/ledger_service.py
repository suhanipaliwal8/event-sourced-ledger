from collections import defaultdict
from uuid import UUID

import psycopg

from app.domain.account import EXTERNAL_ACCOUNT_ID, Account
from app.domain.errors import (
    AccountNotFoundError,
    ConcurrentModificationError,
    CurrencyMismatchError,
    DuplicateTransactionError,
)
from app.domain.money import Money
from app.domain.transaction import Transaction
from app.repositories.accounts import get_account
from app.repositories.ledger_repository import (
    get_account_state,
    get_ledger_total as _get_ledger_total,
    insert_entry,
    insert_transaction,
)


def post_transaction(conn: psycopg.Connection, tx: Transaction) -> Transaction:
    """Save a domain Transaction atomically: all rows, or none.

    `conn` must be an autocommit connection (see app.db.connection.connect), so
    that `conn.transaction()` is a real BEGIN/COMMIT.
    """
    try:
        with conn.transaction():  # BEGIN ... COMMIT, or ROLLBACK on any exception
            accounts = _load_accounts(conn, tx)

            # Net change per account (an account can appear in several entries).
            deltas: dict[UUID, int] = defaultdict(int)
            for entry in tx.entries:
                deltas[entry.account_id] += entry.money.amount

            # Overdraft check. One consistent (balance, version) read per account.
            # Sorted order keeps the processing deterministic (matters in Phase 8).
            next_version: dict[UUID, int] = {}
            for account_id in sorted(deltas):
                balance, last_version = get_account_state(conn, account_id)
                accounts[account_id].new_balance_after(balance, deltas[account_id])
                next_version[account_id] = last_version + 1

            insert_transaction(conn, tx)
            for entry in tx.entries:
                version = next_version[entry.account_id]
                insert_entry(
                    conn, tx.id, entry.account_id, version, entry.money.amount
                )
                next_version[entry.account_id] = version + 1
    except psycopg.errors.UniqueViolation as exc:
        # The rollback has already happened. Translate the DB error into a
        # business error, based on which constraint was violated.
        constraint = exc.diag.constraint_name
        if constraint == "entries_account_version_unique":
            raise ConcurrentModificationError(
                "another writer appended to the same account; please retry"
            ) from exc
        if constraint == "transactions_pkey":
            raise DuplicateTransactionError(
                f"transaction {tx.id} has already been posted"
            ) from exc
        raise
    return tx


def deposit(
    conn: psycopg.Connection,
    account_id: UUID,
    money: Money,
    description: str = "deposit",
) -> Transaction:
    """Money arrives from the outside world: EXTERNAL -x, account +x."""
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, account_id, money, description)
    return post_transaction(conn, tx)


def withdraw(
    conn: psycopg.Connection,
    account_id: UUID,
    money: Money,
    description: str = "withdrawal",
) -> Transaction:
    """Money leaves to the outside world: account -x, EXTERNAL +x."""
    tx = Transaction.transfer(account_id, EXTERNAL_ACCOUNT_ID, money, description)
    return post_transaction(conn, tx)


def transfer(
    conn: psycopg.Connection,
    from_account_id: UUID,
    to_account_id: UUID,
    money: Money,
    description: str = "transfer",
) -> Transaction:
    tx = Transaction.transfer(from_account_id, to_account_id, money, description)
    return post_transaction(conn, tx)


def get_balance(conn: psycopg.Connection, account_id: UUID) -> Money:
    """Current balance, derived by replaying the account's entries."""
    account = get_account(conn, account_id)
    if account is None:
        raise AccountNotFoundError(f"account {account_id} does not exist")
    balance, _ = get_account_state(conn, account_id)
    return Money(balance, account.currency)


def get_ledger_total(conn: psycopg.Connection) -> int:
    """Total of all entries. Must always be 0 in a double-entry ledger."""
    return _get_ledger_total(conn)


def _load_accounts(conn: psycopg.Connection, tx: Transaction) -> dict[UUID, Account]:
    accounts: dict[UUID, Account] = {}
    for entry in tx.entries:
        if entry.account_id not in accounts:
            account = get_account(conn, entry.account_id)
            if account is None:
                raise AccountNotFoundError(f"account {entry.account_id} does not exist")
            accounts[entry.account_id] = account
        if accounts[entry.account_id].currency != entry.money.currency:
            raise CurrencyMismatchError(
                f"entry is in {entry.money.currency} but account "
                f"{entry.account_id} is in {accounts[entry.account_id].currency}"
            )
    return accounts