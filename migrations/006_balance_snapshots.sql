-- A derived, disposable cache: "this account's balance was X as of this version."
-- Never a source of truth. Deleting every row here must not change any answer,
-- only how many entries must be replayed to get it.
CREATE TABLE balance_snapshots (
    account_id      UUID PRIMARY KEY REFERENCES accounts (id),
    account_version BIGINT      NOT NULL,
    balance         BIGINT      NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Snapshots belong to the application's normal read/write path, not to the
-- append-only ledger rules, so the restricted role may UPDATE here (upsert).
GRANT SELECT, INSERT, UPDATE ON balance_snapshots TO ledger_app;