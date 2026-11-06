-- The "outside world". Deposits come from it, withdrawals go to it.
-- Its id must match EXTERNAL_ACCOUNT_ID in app/domain/account.py.
INSERT INTO accounts (id, name, kind, currency, allow_negative)
VALUES ('00000000-0000-0000-0000-000000000001', 'EXTERNAL', 'SYSTEM', 'INR', TRUE);