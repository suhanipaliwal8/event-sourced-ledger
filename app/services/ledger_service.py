import psycopg

from app.domain.account import EXTERNAL_ACCOUNT_ID
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
    get_last_version,
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
            _check_accounts(conn, tx)
            insert_transaction(conn, tx)

            next_version: dict = {}
            for entry in tx.entries:
                if entry.account_id not in next_version:
                    next_version[entry.account_id] = (
                        get_last_version(conn, entry.account_id) + 1
                    )
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
    account_id,
    money: Money,
    description: str = "deposit",
) -> Transaction:
    """Money arrives from the outside world: EXTERNAL -x, account +x."""
    tx = Transaction.transfer(EXTERNAL_ACCOUNT_ID, account_id, money, description)
    return post_transaction(conn, tx)


def _check_accounts(conn: psycopg.Connection, tx: Transaction) -> None:
    accounts: dict = {}
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