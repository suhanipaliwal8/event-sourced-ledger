from app.domain.money import Money
from app.repositories.accounts import create_account
from app.repositories.ledger_repository import get_latest_snapshot
from app.services.audit_service import get_audit_trail
from app.services.ledger_service import deposit, get_balance, withdraw


def replay_balance_ignoring_snapshots(conn, account_id) -> int:
    """The ground truth: SUM over ALL entries, bypassing any snapshot."""
    return conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM entries WHERE account_id = %s",
        (account_id,),
    ).fetchone()[0]


def test_no_snapshot_is_taken_before_the_cadence_is_reached(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    for _ in range(99):
        deposit(ledger_conn, asha.id, Money(10))

    assert get_latest_snapshot(ledger_conn, asha.id) is None


def test_snapshot_is_taken_once_the_cadence_is_crossed(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    for _ in range(100):
        deposit(ledger_conn, asha.id, Money(10))

    snapshot = get_latest_snapshot(ledger_conn, asha.id)
    assert snapshot == (100, 1_000)


def test_balance_matches_full_replay_across_a_snapshot_boundary(ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))
    for i in range(150):
        if i % 3 == 0:
            withdraw(ledger_conn, asha.id, Money(1))
        else:
            deposit(ledger_conn, asha.id, Money(5))

    assert get_latest_snapshot(ledger_conn, asha.id) is not None   # cadence was crossed
    assert (
        get_balance(ledger_conn, asha.id).amount
        == replay_balance_ignoring_snapshots(ledger_conn, asha.id)
    )


def test_deleting_the_snapshot_gives_the_same_balance(ledger_conn):
    """The safety property: snapshots are disposable. Deleting one must not
    change the answer, only how much has to be replayed to get it."""
    asha = create_account(ledger_conn, "Asha")
    for _ in range(120):
        deposit(ledger_conn, asha.id, Money(7))

    with_snapshot = get_balance(ledger_conn, asha.id)
    ledger_conn.execute(
        "DELETE FROM balance_snapshots WHERE account_id = %s", (asha.id,)
    )
    without_snapshot = get_balance(ledger_conn, asha.id)

    assert with_snapshot == without_snapshot


def test_audit_trail_is_unaffected_by_snapshots(ledger_conn):
    """The audit still replays raw entries directly; snapshots must not change
    the running balances it reports."""
    asha = create_account(ledger_conn, "Asha")
    for _ in range(110):
        deposit(ledger_conn, asha.id, Money(3))

    report = get_audit_trail(ledger_conn, asha.id, limit=200)
    assert report.summary.closing_balance == get_balance(ledger_conn, asha.id).amount
    assert report.integrity.ok


def test_multi_entry_transaction_crossing_the_boundary_still_snapshots(ledger_conn):
    """A transfer touches TWO accounts in one transaction; both should be
    checked for crossing the cadence independently."""
    asha = create_account(ledger_conn, "Asha")
    rahul = create_account(ledger_conn, "Rahul")
    deposit(ledger_conn, asha.id, Money(100_000))
    for _ in range(99):
        deposit(ledger_conn, rahul.id, Money(1))   # rahul at version 99

    from app.services.ledger_service import transfer
    transfer(ledger_conn, asha.id, rahul.id, Money(50))   # rahul crosses to version 100

    assert get_latest_snapshot(ledger_conn, rahul.id) is not None