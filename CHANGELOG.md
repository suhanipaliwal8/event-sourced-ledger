# Changelog

## v1.0.0 — Final release

All 7 core requirements and both stretch goals are complete.

### Core
- Event-sourced, append-only ledger with double-entry bookkeeping (Phase 1–3)
- Derived balances and overdraft protection (Phase 4)
- REST API over FastAPI (Phase 5)
- Point-in-time balance queries with backdating (Phase 6)
- Audit trail with independent integrity checks (Phase 7)
- Concurrency control: row locking, deadlock-safe lock ordering, retries (Phase 8)
- Idempotency keys and security hardening: least-privilege DB role, env config, readiness check (Phase 9)

### Stretch goals
- Balance snapshots for faster reads, proven equivalent to full replay (Phase 10)
- Multi-currency transfers via FX clearing accounts (Phase 11)

### Stats
- 203 tests
- 11 phases, each merged as its own reviewed PR with full commit history preserved