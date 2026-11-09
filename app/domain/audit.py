from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Counterparty:
    """Another account that took part in the same transaction."""

    account_id: UUID
    account_name: str
    amount: int  # that account's signed entry amount in the transaction


@dataclass(frozen=True)
class HistoryEntry:
    """One entry of an account's history, exactly as it is stored."""

    entry_id: int
    transaction_id: UUID
    account_version: int
    amount: int
    description: str
    occurred_at: datetime
    recorded_at: datetime
    counterparties: tuple[Counterparty, ...] = ()


@dataclass(frozen=True)
class AuditLine:
    """A history entry plus what we learn by replaying: the running balance."""

    account_version: int
    entry_id: int
    transaction_id: UUID
    description: str
    amount: int
    running_balance: int
    occurred_at: datetime
    recorded_at: datetime
    counterparties: tuple[Counterparty, ...]
    explanation: str


@dataclass(frozen=True)
class AuditSummary:
    entry_count: int
    total_credits: int  # sum of positive entries
    total_debits: int   # sum of negative entries (a negative number)
    opening_balance: int
    closing_balance: int


@dataclass(frozen=True)
class AuditIntegrity:
    balance_matches: bool
    versions_contiguous: bool
    unbalanced_transactions: int

    @property
    def ok(self) -> bool:
        return (
            self.balance_matches
            and self.versions_contiguous
            and self.unbalanced_transactions == 0
        )


@dataclass(frozen=True)
class AuditReport:
    account_id: UUID
    currency: str
    summary: AuditSummary
    integrity: AuditIntegrity
    lines: tuple[AuditLine, ...]          # one page of the history
    next_after_version: int | None        # pass this as after_version for the next page


def replay(history: list[HistoryEntry]) -> tuple[list[AuditLine], AuditSummary]:
    """Rebuild the account's state from its events, one step at a time.

    Entries are applied in account_version order (the order they were recorded).
    """
    balance = 0
    credits = 0
    debits = 0
    lines: list[AuditLine] = []

    for entry in sorted(history, key=lambda h: h.account_version):
        balance += entry.amount
        if entry.amount > 0:
            credits += entry.amount
        else:
            debits += entry.amount
        lines.append(
            AuditLine(
                account_version=entry.account_version,
                entry_id=entry.entry_id,
                transaction_id=entry.transaction_id,
                description=entry.description,
                amount=entry.amount,
                running_balance=balance,
                occurred_at=entry.occurred_at,
                recorded_at=entry.recorded_at,
                counterparties=entry.counterparties,
                explanation=_explain(entry),
            )
        )

    summary = AuditSummary(
        entry_count=len(lines),
        total_credits=credits,
        total_debits=debits,
        opening_balance=0,
        closing_balance=balance,
    )
    return lines, summary


def versions_are_contiguous(history: list[HistoryEntry]) -> bool:
    """True if versions are exactly 1, 2, 3, ... (no gap, no duplicate)."""
    versions = sorted(h.account_version for h in history)
    return versions == list(range(1, len(versions) + 1))


def _explain(entry: HistoryEntry) -> str:
    # dict.fromkeys removes duplicate names but keeps their order.
    names = ", ".join(dict.fromkeys(c.account_name for c in entry.counterparties))
    if entry.amount > 0:
        text = f"Received {entry.amount}"
        if names:
            text += f" from {names}"
    else:
        text = f"Sent {abs(entry.amount)}"
        if names:
            text += f" to {names}"
    return f"{text} ({entry.description})"