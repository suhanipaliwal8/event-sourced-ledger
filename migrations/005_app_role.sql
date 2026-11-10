-- A restricted role for the RUNNING application: it can read and append,
-- but cannot change history, drop triggers, or create objects.
-- The role cannot log in by itself; a login user is made a member of it
-- outside of migrations (so no password is ever committed to git).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledger_app') THEN
        CREATE ROLE ledger_app NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO ledger_app;
GRANT SELECT, INSERT ON accounts, transactions, entries TO ledger_app;

-- SELECT ... FOR UPDATE (our account lock) needs UPDATE privilege on at least one
-- column. Granting it only on the harmless "name" column keeps "kind" and
-- "allow_negative" read-only for the application.
GRANT UPDATE (name) ON accounts TO ledger_app;