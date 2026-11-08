from uuid import uuid4

from app.domain.account import EXTERNAL_ACCOUNT_ID
from app.services.ledger_service import get_ledger_total


# ---------- helpers ----------
def create_account(client, name="Asha", currency="INR") -> str:
    r = client.post("/accounts", json={"name": name, "currency": currency})
    assert r.status_code == 201
    return r.json()["id"]


def deposit(client, account_id, amount, currency="INR"):
    return client.post(
        f"/accounts/{account_id}/deposits",
        json={"amount": amount, "currency": currency},
    )


def withdraw(client, account_id, amount, currency="INR"):
    return client.post(
        f"/accounts/{account_id}/withdrawals",
        json={"amount": amount, "currency": currency},
    )


def transfer(client, from_id, to_id, amount, currency="INR"):
    return client.post(
        "/transfers",
        json={
            "from_account_id": from_id,
            "to_account_id": to_id,
            "amount": amount,
            "currency": currency,
            "description": "test transfer",
        },
    )


def balance(client, account_id) -> int:
    r = client.get(f"/accounts/{account_id}/balance")
    assert r.status_code == 200
    return r.json()["amount"]


# ---------- accounts ----------
def test_create_account_returns_201(client):
    r = client.post("/accounts", json={"name": "Asha", "currency": "INR"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Asha"
    assert body["kind"] == "CUSTOMER"
    assert body["allow_negative"] is False


def test_create_account_rejects_lowercase_currency(client):
    r = client.post("/accounts", json={"name": "Asha", "currency": "inr"})
    assert r.status_code == 422


def test_create_account_rejects_blank_name(client):
    r = client.post("/accounts", json={"name": "   ", "currency": "INR"})
    assert r.status_code == 422


def test_get_account_returns_account(client):
    account_id = create_account(client, "Rahul")
    r = client.get(f"/accounts/{account_id}")
    assert r.status_code == 200
    assert r.json()["id"] == account_id
    assert r.json()["name"] == "Rahul"


def test_get_unknown_account_returns_404(client):
    r = client.get(f"/accounts/{uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "account_not_found"


def test_invalid_uuid_returns_422(client):
    r = client.get("/accounts/not-a-uuid")
    assert r.status_code == 422


def test_new_account_balance_is_zero(client):
    account_id = create_account(client)
    assert balance(client, account_id) == 0


# ---------- deposits ----------
def test_deposit_returns_201_and_updates_balance(client):
    asha = create_account(client)
    r = deposit(client, asha, 10_000)
    assert r.status_code == 201

    amounts = {e["account_id"]: e["amount"] for e in r.json()["entries"]}
    assert amounts[asha] == 10_000
    assert amounts[str(EXTERNAL_ACCOUNT_ID)] == -10_000
    assert balance(client, asha) == 10_000


def test_deposit_rejects_float_amount(client):
    asha = create_account(client)
    r = deposit(client, asha, 10.5)
    assert r.status_code == 422
    assert balance(client, asha) == 0


def test_deposit_rejects_zero_amount(client):
    asha = create_account(client)
    r = deposit(client, asha, 0)
    assert r.status_code == 422


def test_deposit_to_unknown_account_returns_404(client):
    r = deposit(client, str(uuid4()), 100)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "account_not_found"


def test_deposit_with_wrong_currency_returns_422(client):
    asha = create_account(client, currency="INR")
    r = deposit(client, asha, 100, currency="USD")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "currency_mismatch"
    assert balance(client, asha) == 0


# ---------- withdrawals ----------
def test_withdraw_reduces_balance(client):
    asha = create_account(client)
    deposit(client, asha, 1_000)
    r = withdraw(client, asha, 400)
    assert r.status_code == 201
    assert balance(client, asha) == 600


def test_withdraw_more_than_balance_returns_409(client):
    asha = create_account(client)
    deposit(client, asha, 1_000)
    r = withdraw(client, asha, 1_500)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insufficient_funds"
    assert balance(client, asha) == 1_000


# ---------- transfers ----------
def test_transfer_moves_money(client):
    asha = create_account(client, "Asha")
    rahul = create_account(client, "Rahul")
    deposit(client, asha, 5_000)

    r = transfer(client, asha, rahul, 2_000)
    assert r.status_code == 201
    assert balance(client, asha) == 3_000
    assert balance(client, rahul) == 2_000


def test_transfer_with_insufficient_funds_returns_409_and_changes_nothing(client):
    asha = create_account(client, "Asha")
    rahul = create_account(client, "Rahul")
    deposit(client, asha, 500)

    r = transfer(client, asha, rahul, 800)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insufficient_funds"
    assert balance(client, asha) == 500
    assert balance(client, rahul) == 0


def test_transfer_to_same_account_returns_422(client):
    asha = create_account(client)
    deposit(client, asha, 500)
    r = transfer(client, asha, asha, 100)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_transaction"


def test_transfer_with_unknown_account_returns_404(client):
    asha = create_account(client)
    deposit(client, asha, 500)
    r = transfer(client, asha, str(uuid4()), 100)
    assert r.status_code == 404


def test_transfer_with_missing_field_returns_422(client):
    asha = create_account(client)
    r = client.post("/transfers", json={"from_account_id": asha})
    assert r.status_code == 422


# ---------- security ----------
def test_cannot_transfer_out_of_external_account(client):
    """Otherwise a client could mint money for free."""
    asha = create_account(client)
    r = transfer(client, str(EXTERNAL_ACCOUNT_ID), asha, 1_000)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "system_account_not_allowed"
    assert balance(client, asha) == 0


def test_cannot_deposit_into_external_account(client):
    r = deposit(client, str(EXTERNAL_ACCOUNT_ID), 1_000)
    assert r.status_code == 403


# ---------- whole-system check ----------
def test_ledger_total_stays_zero_after_api_activity(client, ledger_conn):
    asha = create_account(client, "Asha")
    rahul = create_account(client, "Rahul")
    deposit(client, asha, 9_000)
    transfer(client, asha, rahul, 4_000)
    withdraw(client, rahul, 1_500)
    withdraw(client, asha, 999_999)          # rejected, must leave no trace

    assert get_ledger_total(ledger_conn) == 0