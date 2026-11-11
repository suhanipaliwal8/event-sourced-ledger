import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from app.domain.account import EXTERNAL_ACCOUNT_ID, Account
from app.domain.entry import Entry
from app.domain.errors import (
    AccountNotFoundError,
    ConcurrentModificationError,
    CurrencyMismatchError,
    DuplicateTransactionError,
    FutureTransactionError,
    IdempotencyKeyReusedError,
    InvalidTransactionError,

)
from app.domain.money import Money
from app.domain.transaction import Transaction
from app.repositories.accounts import (
    get_account,
    get_or_create_external_account,
    get_or_create_fx_clearing_account,
    lock_account,
)
from app.repositories.ledger_repository import (
    find_transaction_by_idempotency_key,
    get_account_state,
    get_balance_at,
    get_ledger_total as _get_ledger_total,
    get_ledger_totals_by_currency as _get_ledger_totals_by_currency,
    insert_entry,
    insert_transaction,
    save_snapshot,
)

# How long a writer waits for another writer's account lock before giving up.
LOCK_TIMEOUT = "5s"
# How many times a conflicting post is attempted in total.
MAX_ATTEMPTS = 3
# How often (in entries) a snapshot is refreshed for an account.
SNAPSHOT_EVERY_N_ENTRIES = 100


def post_transaction(
    conn: psycopg.Connection, tx: Transaction, max_attempts: int = MAX_ATTEMPTS
) -> Transaction:
    """Save a domain Transaction atomically: all rows, or none.

    `conn` must be an autocommit connection (see app.db.connection.connect), so
    that `conn.transaction()` is a real BEGIN/COMMIT.

    Transactions may be backdated, but never future-dated. That keeps
    "balance as of now" identical to the current balance.

    If tx.idempotency_key was already used for the SAME request, the stored
    transaction is returned and nothing new is written (a replay).

    Transient conflicts (ConcurrentModificationError) are retried a few times
    with a short random pause. Business errors are NEVER retried.
    """
    if tx.occurred_at > datetime.now(timezone.utc):
        raise FutureTransactionError(
            "occurred_at is in the future; transactions can only be dated now or earlier"
        )

    attempt = 0
    while True:
        attempt += 1
        try:
            return _post_once(conn, tx)
        except ConcurrentModificationError:
            if attempt >= max_attempts:
                raise
            time.sleep(random.uniform(0.005, 0.02) * attempt)   # backoff, then try again


def _post_once(conn: psycopg.Connection, tx: Transaction) -> Transaction:
    """One attempt: a single database transaction."""
    try:
        with conn.transaction():  # BEGIN ... COMMIT, or ROLLBACK on any exception
            # Never wait forever for somebody else's lock (applies to this transaction only).
            conn.execute("SELECT set_config('lock_timeout', %s, true)", (LOCK_TIMEOUT,))

            accounts = _load_accounts(conn, tx)

            # Net change per account (an account can appear in several entries).
            deltas: dict[UUID, int] = defaultdict(int)
            for entry in tx.entries:
                deltas[entry.account_id] += entry.money.amount

            # LOCK every affected account, ALWAYS in sorted order. Two transfers
            # A->B and B->A therefore both lock the lower id first, so they queue
            # instead of deadlocking.
            sorted_ids = sorted(deltas)
            for account_id in sorted_ids:
                lock_account(conn, account_id)

            # IDEMPOTENCY: checked AFTER the locks. If an identical request is
            # racing us, we waited for its lock and can now see its committed row.
            # Checking first could wrongly report "insufficient funds" for a replay.
            if tx.idempotency_key is not None:
                existing = find_transaction_by_idempotency_key(conn, tx.idempotency_key)
                if existing is not None:
                    return _resolve_replay(existing, tx)

            # Overdraft check. One consistent (balance, version) read per account.
            # NOTE: this checks the balance NOW, not at the transaction's occurred_at.
            next_version: dict[UUID, int] = {}
            for account_id in sorted_ids:
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

            # Opportunistic snapshotting: after this account crosses a multiple of
            # SNAPSHOT_EVERY_N_ENTRIES, refresh its snapshot in the SAME database
            # transaction, so the snapshot's version is always consistent with what
            # was just committed. This never changes the account's balance, only
            # how much history a future read has to replay.
            for account_id in sorted_ids:
                new_version = next_version[account_id] - 1
                if new_version // SNAPSHOT_EVERY_N_ENTRIES > (
                    (new_version - deltas_count(tx, account_id)) // SNAPSHOT_EVERY_N_ENTRIES
                ):
                    balance, _ = get_account_state(conn, account_id)
                    save_snapshot(conn, account_id, new_version, balance)
    except psycopg.errors.UniqueViolation as exc:
        # The rollback has already happened. Translate the DB error into a
        # business outcome, based on which constraint was violated.
        constraint = exc.diag.constraint_name
        if constraint == "entries_account_version_unique":
            # Safety net: someone appended without waiting for our lock.
            raise ConcurrentModificationError(
                "another writer appended to the same account; please retry"
            ) from exc
        if constraint == "transactions_pkey":
            raise DuplicateTransactionError(
                f"transaction {tx.id} has already been posted"
            ) from exc
        if constraint == "transactions_idempotency_key_key":
            # A request with this key committed between our check and our insert.
            existing = find_transaction_by_idempotency_key(conn, tx.idempotency_key)
            if existing is None:
                raise ConcurrentModificationError(
                    "idempotency key is being processed; please retry"
                ) from exc
            return _resolve_replay(existing, tx)
        raise
    except psycopg.errors.LockNotAvailable as exc:
        raise ConcurrentModificationError(
            "timed out waiting for another writer; please retry"
        ) from exc
    except psycopg.errors.DeadlockDetected as exc:
        raise ConcurrentModificationError("deadlock detected; please retry") from exc
    return tx


def _resolve_replay(existing: Transaction, requested: Transaction) -> Transaction:
    """The key was used before: replay the original, unless the request differs."""
    if not existing.same_request_as(requested):
        raise IdempotencyKeyReusedError(
            "this idempotency key was already used for a different request"
        )
    return existing


def deposit(
    conn: psycopg.Connection,
    account_id: UUID,
    money: Money,
    description: str = "deposit",
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> Transaction:
    """Money arrives from the outside world: EXTERNAL(currency) -x, account +x."""
    external = get_or_create_external_account(conn, money.currency)
    tx = Transaction.transfer(
        external.id, account_id, money, description, occurred_at, idempotency_key
    )
    return post_transaction(conn, tx)


def withdraw(
    conn: psycopg.Connection,
    account_id: UUID,
    money: Money,
    description: str = "withdrawal",
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> Transaction:
    """Money leaves to the outside world: account -x, EXTERNAL(currency) +x."""
    external = get_or_create_external_account(conn, money.currency)
    tx = Transaction.transfer(
        account_id, external.id, money, description, occurred_at, idempotency_key
    )
    return post_transaction(conn, tx)


def transfer(
    conn: psycopg.Connection,
    from_account_id: UUID,
    to_account_id: UUID,
    money: Money,
    description: str = "transfer",
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> Transaction:
    tx = Transaction.transfer(
        from_account_id, to_account_id, money, description, occurred_at, idempotency_key
    )
    return post_transaction(conn, tx)


def get_balance(conn: psycopg.Connection, account_id: UUID) -> Money:
    """Current balance, derived by replaying the account's entries."""
    account = get_account(conn, account_id)
    if account is None:
        raise AccountNotFoundError(f"account {account_id} does not exist")
    balance, _ = get_account_state(conn, account_id)
    return Money(balance, account.currency)


def get_balance_as_of(
    conn: psycopg.Connection,
    account_id: UUID,
    as_of: datetime,
    known_at: datetime | None = None,
) -> Money:
    """Balance as of a moment in time (inclusive).

    as_of:    only entries that OCCURRED by then count.
    known_at: if given, only entries our ledger had RECORDED by then count too,
              i.e. "what did the books say at that moment?".
    """
    if as_of.tzinfo is None or (known_at is not None and known_at.tzinfo is None):
        raise ValueError("as_of and known_at must be timezone-aware datetimes")
    account = get_account(conn, account_id)
    if account is None:
        raise AccountNotFoundError(f"account {account_id} does not exist")
    amount = get_balance_at(conn, account_id, as_of, known_at)
    return Money(amount, account.currency)


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

def deltas_count(tx: Transaction, account_id: UUID) -> int:
    """How many of this transaction's entries touched this account (usually 1)."""
    return sum(1 for e in tx.entries if e.account_id == account_id)

def fx_transfer(
    conn: psycopg.Connection,
    from_account_id: UUID,
    send_money: Money,
    to_account_id: UUID,
    receive_money: Money,
    description: str = "fx transfer",
    occurred_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> Transaction:
    """Move money between accounts of DIFFERENT currencies, at a rate implied
    by the two amounts (receive_money.amount / send_money.amount), locked in
    at posting time.

    Built as 4 entries through each currency's FX clearing account, so each
    currency balances on its own (see module docstring in README: "Snapshots"
    and "Multi-currency" sections).
    """
    if from_account_id == to_account_id:
        raise InvalidTransactionError("cannot transfer to the same account")
    if send_money.amount <= 0 or receive_money.amount <= 0:
        raise InvalidTransactionError("send and receive amounts must be positive")
    if send_money.currency == receive_money.currency:
        raise InvalidTransactionError(
            "send and receive currencies are the same; use transfer() instead"
        )

    send_clearing = get_or_create_fx_clearing_account(conn, send_money.currency)
    receive_clearing = get_or_create_fx_clearing_account(conn, receive_money.currency)

    tx = Transaction(
        description=description,
        entries=(
            Entry(from_account_id, -send_money),
            Entry(send_clearing.id, send_money),
            Entry(receive_clearing.id, -receive_money),
            Entry(to_account_id, receive_money),
        ),
        occurred_at=occurred_at or datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
    )
    return post_transaction(conn, tx)


def get_ledger_totals_by_currency(conn: psycopg.Connection) -> dict[str, int]:
    """Per-currency ledger totals. Every value must always be 0."""
    return _get_ledger_totals_by_currency(conn)