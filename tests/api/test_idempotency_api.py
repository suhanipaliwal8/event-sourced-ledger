from uuid import uuid4


def create_account(client, name="Asha") -> str:
    r = client.post("/accounts", json={"name": name, "currency": "INR"})
    assert r.status_code == 201
    return r.json()["id"]


def balance(client, account_id) -> int:
    return client.get(f"/accounts/{account_id}/balance").json()["amount"]


def key_header(key=None) -> dict:
    return {"Idempotency-Key": key or f"key-{uuid4()}"}


def test_same_key_returns_the_same_transaction_and_posts_once(client):
    asha = create_account(client)
    headers = key_header()
    body = {"amount": 1_000, "currency": "INR"}

    first = client.post(f"/accounts/{asha}/deposits", json=body, headers=headers)
    second = client.post(f"/accounts/{asha}/deposits", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert balance(client, asha) == 1_000


def test_reusing_a_key_with_a_different_payload_returns_409(client):
    asha = create_account(client)
    headers = key_header()

    client.post(
        f"/accounts/{asha}/deposits", json={"amount": 1_000, "currency": "INR"}, headers=headers
    )
    r = client.post(
        f"/accounts/{asha}/deposits", json={"amount": 2_000, "currency": "INR"}, headers=headers
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "idempotency_key_reused"
    assert balance(client, asha) == 1_000


def test_transfer_supports_idempotency_keys(client):
    asha = create_account(client, "Asha")
    rahul = create_account(client, "Rahul")
    client.post(f"/accounts/{asha}/deposits", json={"amount": 1_000, "currency": "INR"})
    headers = key_header()
    body = {
        "from_account_id": asha,
        "to_account_id": rahul,
        "amount": 300,
        "currency": "INR",
        "description": "rent",
    }

    first = client.post("/transfers", json=body, headers=headers)
    second = client.post("/transfers", json=body, headers=headers)

    assert second.json()["id"] == first.json()["id"]
    assert balance(client, asha) == 700
    assert balance(client, rahul) == 300


def test_blank_idempotency_key_returns_422(client):
    asha = create_account(client)
    r = client.post(
        f"/accounts/{asha}/deposits",
        json={"amount": 100, "currency": "INR"},
        headers={"Idempotency-Key": "   "},
    )
    assert r.status_code == 422
    assert balance(client, asha) == 0


def test_overlong_idempotency_key_returns_422(client):
    asha = create_account(client)
    r = client.post(
        f"/accounts/{asha}/deposits",
        json={"amount": 100, "currency": "INR"},
        headers={"Idempotency-Key": "k" * 256},
    )
    assert r.status_code == 422