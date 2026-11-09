import random
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.connection import connect
from app.domain.errors import ConcurrentModificationError, InsufficientFundsError
from app.domain.money import Money
from app.repositories.accounts import create_account
from app.services import ledger_service
from app.services.audit_service import get_audit_trail
from app.services.ledger_service import (
    deposit,
    get_balance,
    get_ledger_total,
    transfer,
    withdraw,
)


def run_concurrently(db_url: str, jobs: list) -> list:
    """Run every job in its own thread with its OWN database connection.

    All threads wait at a barrier and are released together, so the jobs really
    collide. Returns one outcome per job: None on success, or the exception raised.
    """
    barrier = threading.Barrier(len(jobs))

    def worker(job):
        conn = connect(db_url)
        try:
            barrier.wait(timeout=10)
            try:
                job(conn)
                return None
            except Exception as exc:        # we WANT to inspect failures
                return exc
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(worker, jobs))


# ---------- the race conditions ----------
def test_concurrent_withdrawals_never_overdraw(db_url, ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    deposit(ledger_conn, asha.id, Money(1_000))

    # 20 withdrawals of 100 against a balance of 1000: exactly 10 can succeed.
    outcomes = run_concurrently(db_url, [lambda c: withdraw(c, asha.id, Money(100))] * 20)

    successes = [o for o in outcomes if o is None]
    failures = [o for o in outcomes if o is not None]
    assert len(successes) == 10
    assert all(isinstance(f, InsufficientFundsError) for f in failures)
    assert get_balance(ledger_conn, asha.id) == Money(0)
    assert get_audit_trail(ledger_conn, asha.id).integrity.ok


def test_concurrent_deposits_lose_no_update(db_url, ledger_conn):
    asha = create_account(ledger_conn, "Asha")

    outcomes = run_concurrently(db_url, [lambda c: deposit(c, asha.id, Money(50))] * 20)

    assert all(o is None for o in outcomes)               # nobody was rejected
    assert get_balance(ledger_conn, asha.id) == Money(1_000)
    report = get_audit_trail(ledger_conn, asha.id)
    assert report.summary.entry_count == 20
    assert report.integrity.ok


def test_opposite_transfers_do_not_deadlock(db_url, ledger_conn):
    a = create_account(ledger_conn, "A")
    b = create_account(ledger_conn, "B")
    deposit(ledger_conn, a.id, Money(10_000))
    deposit(ledger_conn, b.id, Money(10_000))

    jobs = (
        [lambda c: transfer(c, a.id, b.id, Money(100))] * 10
        + [lambda c: transfer(c, b.id, a.id, Money(100))] * 10
    )
    outcomes = run_concurrently(db_url, jobs)

    assert all(o is None for o in outcomes)               # no deadlock, no conflict
    assert get_balance(ledger_conn, a.id) == Money(10_000)
    assert get_balance(ledger_conn, b.id) == Money(10_000)


def test_random_concurrent_transfers_conserve_money(db_url, ledger_conn):
    rng = random.Random(42)
    accounts = [create_account(ledger_conn, f"Acc{i}") for i in range(5)]
    for account in accounts:
        deposit(ledger_conn, account.id, Money(1_000))     # 5,000 in total

    jobs = []
    for _ in range(40):
        src, dst = rng.sample(accounts, 2)
        amount = rng.randint(1, 600)
        jobs.append(lambda c, s=src, d=dst, a=amount: transfer(c, s.id, d.id, Money(a)))

    outcomes = run_concurrently(db_url, jobs)

    for outcome in outcomes:
        assert outcome is None or isinstance(outcome, InsufficientFundsError)

    balances = [get_balance(ledger_conn, a.id).amount for a in accounts]
    assert sum(balances) == 5_000                          # money neither created nor lost
    assert all(balance >= 0 for balance in balances)
    assert get_ledger_total(ledger_conn) == 0
    for account in accounts:
        assert get_audit_trail(ledger_conn, account.id).integrity.ok


# ---------- locking behaviour, tested deterministically ----------
def test_writer_waits_for_a_held_lock_instead_of_failing(db_url, ledger_conn):
    asha = create_account(ledger_conn, "Asha")
    finished = threading.Event()
    result = {}

    def writer():
        conn = connect(db_url)
        try:
            deposit(conn, asha.id, Money(100))
            result["ok"] = True
        except Exception as exc:
            result["error"] = exc
        finally:
            conn.close()
            finished.set()

    holder = connect(db_url)
    try:
        with holder.transaction():       # BEGIN ... COMMIT when the block ends
            holder.execute("SELECT 1 FROM accounts WHERE id = %s FOR UPDATE", (asha.id,))
            thread = threading.Thread(target=writer)
            thread.start()
            assert not finished.wait(timeout=0.5)      # still blocked while we hold the lock
        thread.join(timeout=10)                        # lock released: the writer finishes
    finally:
        holder.close()

    assert result == {"ok": True}
    assert get_balance(ledger_conn, asha.id) == Money(100)


def test_lock_timeout_becomes_concurrent_modification_error(db_url, ledger_conn, monkeypatch):
    monkeypatch.setattr(ledger_service, "LOCK_TIMEOUT", "100ms")
    asha = create_account(ledger_conn, "Asha")

    holder = connect(db_url)
    try:
        with holder.transaction():
            holder.execute("SELECT 1 FROM accounts WHERE id = %s FOR UPDATE", (asha.id,))
            writer_conn = connect(db_url)
            try:
                with pytest.raises(ConcurrentModificationError):
                    deposit(writer_conn, asha.id, Money(100))
            finally:
                writer_conn.close()
    finally:
        holder.close()

    assert get_balance(ledger_conn, asha.id) == Money(0)


# ---------- retry ----------
def test_retry_succeeds_after_transient_conflicts(ledger_conn, monkeypatch):
    asha = create_account(ledger_conn, "Asha")
    real_post_once = ledger_service._post_once
    calls = {"n": 0}

    def flaky(conn, tx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConcurrentModificationError("simulated conflict")
        return real_post_once(conn, tx)

    monkeypatch.setattr(ledger_service, "_post_once", flaky)

    deposit(ledger_conn, asha.id, Money(100))

    assert calls["n"] == 3
    assert get_balance(ledger_conn, asha.id) == Money(100)


def test_retry_gives_up_after_max_attempts(ledger_conn, monkeypatch):
    asha = create_account(ledger_conn, "Asha")
    calls = {"n": 0}

    def always_conflict(conn, tx):
        calls["n"] += 1
        raise ConcurrentModificationError("simulated conflict")

    monkeypatch.setattr(ledger_service, "_post_once", always_conflict)

    with pytest.raises(ConcurrentModificationError):
        deposit(ledger_conn, asha.id, Money(100))
    assert calls["n"] == ledger_service.MAX_ATTEMPTS