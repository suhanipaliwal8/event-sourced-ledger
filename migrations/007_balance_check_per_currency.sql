-- Supersedes migration 003's check: a transaction must balance WITHIN EACH
-- CURRENCY, not as one global sum (which is meaningless across currencies).
-- A single-currency transaction is the special case of one currency group,
-- so every pre-existing transaction remains valid under this stricter rule.
CREATE OR REPLACE FUNCTION check_transaction_balanced() RETURNS trigger AS $$
DECLARE
    bad_currency TEXT;
    bad_total BIGINT;
BEGIN
    SELECT a.currency, SUM(e.amount)
    INTO bad_currency, bad_total
    FROM entries e
    JOIN accounts a ON a.id = e.account_id
    WHERE e.transaction_id = NEW.transaction_id
    GROUP BY a.currency
    HAVING SUM(e.amount) <> 0
    LIMIT 1;

    IF bad_currency IS NOT NULL THEN
        RAISE EXCEPTION 'transaction % is unbalanced in %: entries sum to %',
            NEW.transaction_id, bad_currency, bad_total
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;