-- Rule 1: the entries of a transaction must sum to zero.
CREATE FUNCTION check_transaction_balanced() RETURNS trigger AS $$
DECLARE
    total BIGINT;
BEGIN
    SELECT COALESCE(SUM(amount), 0) INTO total
    FROM entries
    WHERE transaction_id = NEW.transaction_id;

    IF total <> 0 THEN
        RAISE EXCEPTION 'transaction % is unbalanced: entries sum to %',
            NEW.transaction_id, total
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- DEFERRABLE INITIALLY DEFERRED = run this at COMMIT, not after each insert.
CREATE CONSTRAINT TRIGGER entries_must_balance
    AFTER INSERT ON entries
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_transaction_balanced();

-- Rule 2: a transaction must have at least 2 entries.
CREATE FUNCTION check_transaction_has_entries() RETURNS trigger AS $$
DECLARE
    entry_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO entry_count
    FROM entries
    WHERE transaction_id = NEW.id;

    IF entry_count < 2 THEN
        RAISE EXCEPTION 'transaction % has % entries, at least 2 are required',
            NEW.id, entry_count
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER transactions_must_have_entries
    AFTER INSERT ON transactions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_transaction_has_entries();