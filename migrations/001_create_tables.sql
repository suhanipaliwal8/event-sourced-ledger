-- Accounts: reference data (who can hold money).
CREATE TABLE accounts (
    id             UUID PRIMARY KEY,
    name           TEXT        NOT NULL,
    kind           TEXT        NOT NULL CHECK (kind IN ('CUSTOMER', 'SYSTEM')),
    currency       CHAR(3)     NOT NULL,
    -- SYSTEM accounts (e.g. EXTERNAL, the "outside world") may go negative.
    allow_negative BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Transactions: one row per business event. Immutable.
CREATE TABLE transactions (
    id              UUID PRIMARY KEY,
    description     TEXT        NOT NULL,
    -- Lets a client safely retry a request (used in Phase 9). NULLs are allowed
    -- and do not conflict with each other.
    idempotency_key TEXT        UNIQUE,
    occurred_at     TIMESTAMPTZ NOT NULL,                -- when it happened in the real world
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()   -- when we saved it
);

-- Entries: the ledger lines (the events). Append-only.
CREATE TABLE entries (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id  UUID   NOT NULL REFERENCES transactions (id),
    account_id      UUID   NOT NULL REFERENCES accounts (id),
    -- Position of this entry in the account's own history: 1, 2, 3, ...
    account_version BIGINT NOT NULL CHECK (account_version >= 1),
    -- Signed minor units (paise). Positive = into the account, negative = out.
    amount          BIGINT NOT NULL CHECK (amount <> 0),
    CONSTRAINT entries_account_version_unique UNIQUE (account_id, account_version)
);

CREATE INDEX entries_transaction_id_idx ON entries (transaction_id);