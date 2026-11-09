from datetime import datetime, timezone
from uuid import uuid4

from app.domain.audit import (
    AuditIntegrity,
    Counterparty,
    HistoryEntry,
    replay,
    versions_are_contiguous,
)

WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def entry(version, amount, description="test", counterparty="EXTERNAL") -> HistoryEntry:
    return HistoryEntry(
        entry_id=version,
        transaction_id=uuid4(),
        account_version=version,
        amount=amount,
        description=description,
        occurred_at=WHEN,
        recorded_at=WHEN,
        counterparties=(Counterparty(uuid4(), counterparty, -amount),),
    )


def test_replay_computes_running_balance():
    lines, summary = replay([entry(1, 1_000), entry(2, -300), entry(3, 200)])
    assert [line.running_balance for line in lines] == [1_000, 700, 900]
    assert summary.closing_balance == 900


def test_replay_computes_totals():
    _, summary = replay([entry(1, 1_000), entry(2, -300), entry(3, 200)])
    assert summary.entry_count == 3
    assert summary.total_credits == 1_200
    assert summary.total_debits == -300
    assert summary.opening_balance == 0


def test_replay_orders_by_version_even_if_input_is_unordered():
    lines, _ = replay([entry(2, 200), entry(1, 1_000)])
    assert [line.account_version for line in lines] == [1, 2]
    assert [line.running_balance for line in lines] == [1_000, 1_200]


def test_replay_of_empty_history():
    lines, summary = replay([])
    assert lines == []
    assert summary.closing_balance == 0
    assert summary.entry_count == 0


def test_explanation_for_a_credit_names_the_counterparty():
    lines, _ = replay([entry(1, 1_000, "deposit", "EXTERNAL")])
    assert lines[0].explanation == "Received 1000 from EXTERNAL (deposit)"


def test_explanation_for_a_debit_names_the_counterparty():
    lines, _ = replay([entry(1, -300, "rent", "Rahul")])
    assert lines[0].explanation == "Sent 300 to Rahul (rent)"


def test_contiguous_versions_are_accepted():
    assert versions_are_contiguous([entry(1, 10), entry(2, 10), entry(3, 10)])


def test_gap_in_versions_is_detected():
    assert not versions_are_contiguous([entry(1, 10), entry(3, 10)])


def test_integrity_is_ok_only_if_every_check_passes():
    assert AuditIntegrity(True, True, 0).ok
    assert not AuditIntegrity(False, True, 0).ok
    assert not AuditIntegrity(True, False, 0).ok
    assert not AuditIntegrity(True, True, 1).ok