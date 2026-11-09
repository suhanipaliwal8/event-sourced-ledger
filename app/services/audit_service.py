from uuid import UUID

import psycopg

from app.domain.audit import (
    AuditIntegrity,
    AuditReport,
    replay,
    versions_are_contiguous,
)
from app.domain.errors import AccountNotFoundError
from app.repositories.accounts import get_account
from app.repositories.audit_repository import (
    count_unbalanced_transactions,
    get_account_history,
)
from app.repositories.ledger_repository import get_account_state


def get_audit_trail(
    conn: psycopg.Connection,
    account_id: UUID,
    after_version: int = 0,
    limit: int = 50,
) -> AuditReport:
    """Replay an account's whole history and explain how it reached its balance.

    The summary and integrity checks always cover the FULL history. Only the
    returned `lines` are paged (entries with account_version > after_version).
    """
    # One read-only REPEATABLE READ transaction = ONE consistent snapshot for all
    # the queries below. Without it, a deposit committing between two queries
    # could make the audit report a false mismatch.
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

        account = get_account(conn, account_id)
        if account is None:
            raise AccountNotFoundError(f"account {account_id} does not exist")

        history = get_account_history(conn, account_id)
        current_balance, _ = get_account_state(conn, account_id)   # independent SUM
        unbalanced = count_unbalanced_transactions(conn, account_id)

    lines, summary = replay(history)
    integrity = AuditIntegrity(
        balance_matches=summary.closing_balance == current_balance,
        versions_contiguous=versions_are_contiguous(history),
        unbalanced_transactions=unbalanced,
    )

    page = [line for line in lines if line.account_version > after_version][:limit]
    has_more = bool(page) and page[-1].account_version < lines[-1].account_version
    next_after_version = page[-1].account_version if has_more else None

    return AuditReport(
        account_id=account_id,
        currency=account.currency,
        summary=summary,
        integrity=integrity,
        lines=tuple(page),
        next_after_version=next_after_version,
    )