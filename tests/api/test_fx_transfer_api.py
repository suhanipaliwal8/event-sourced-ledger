def create_account(client, name, currency) -> str:
    r = client.post("/accounts", json={"name": name, "currency": currency})
    assert r.status_code == 201
    return r.json()["id"]


def deposit(client, account_id, amount, currency):
    r = client.post(
        f"/accounts/{account_id}/deposits", json={"amount": amount, "currency": currency}
    )
    assert r.status_code == 201


def balance(client, account_id) -> int:
    return client.get(f"/accounts/{account_id}/balance").json()["amount"]


def test_fx_transfer_moves_money_between_currencies(client):
    asha = create_account(client, "Asha", "USD")
    rahul = create_account(client, "Rahul", "INR")
    deposit(client, asha, 10_000, "USD")

    r = client.post(
        "/fx-transfers",
        json={
            "from_account_id": asha,
            "to_account_id": rahul,
            "send_amount": 10_000,
            "send_currency": "USD",
            "receive_amount": 830_000,
            "receive_currency": "INR",
        },
    )
    assert r.status_code == 201
    assert balance(client, asha) == 0
    assert balance(client, rahul) == 830_000


def test_same_currency_fx_transfer_returns_422(client):
    asha = create_account(client, "Asha", "USD")
    rahul = create_account(client, "Rahul", "USD")
    deposit(client, asha, 100, "USD")

    r = client.post(
        "/fx-transfers",
        json={
            "from_account_id": asha,
            "to_account_id": rahul,
            "send_amount": 100,
            "send_currency": "USD",
            "receive_amount": 100,
            "receive_currency": "USD",
        },
    )
    assert r.status_code == 422


def test_fx_transfer_with_insufficient_funds_returns_409(client):
    asha = create_account(client, "Asha", "USD")
    rahul = create_account(client, "Rahul", "INR")
    deposit(client, asha, 10, "USD")

    r = client.post(
        "/fx-transfers",
        json={
            "from_account_id": asha,
            "to_account_id": rahul,
            "send_amount": 10_000,
            "send_currency": "USD",
            "receive_amount": 830_000,
            "receive_currency": "INR",
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "insufficient_funds"


def test_fx_transfer_with_unknown_account_returns_404(client):
    import uuid

    asha = create_account(client, "Asha", "USD")
    deposit(client, asha, 100, "USD")

    r = client.post(
        "/fx-transfers",
        json={
            "from_account_id": asha,
            "to_account_id": str(uuid.uuid4()),
            "send_amount": 100,
            "send_currency": "USD",
            "receive_amount": 8_300,
            "receive_currency": "INR",
        },
    )
    assert r.status_code == 404


def test_fx_transfer_rejects_system_accounts(client):
    from app.domain.account import EXTERNAL_ACCOUNT_ID

    rahul = create_account(client, "Rahul", "INR")
    r = client.post(
        "/fx-transfers",
        json={
            "from_account_id": str(EXTERNAL_ACCOUNT_ID),
            "to_account_id": rahul,
            "send_amount": 100,
            "send_currency": "USD",
            "receive_amount": 8_300,
            "receive_currency": "INR",
        },
    )
    assert r.status_code == 403