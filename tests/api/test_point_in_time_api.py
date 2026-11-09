from datetime import datetime, timedelta, timezone


def ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def create_account(client, name="Asha") -> str:
    r = client.post("/accounts", json={"name": name, "currency": "INR"})
    assert r.status_code == 201
    return r.json()["id"]


def deposit(client, account_id, amount, occurred_at=None):
    body = {"amount": amount, "currency": "INR"}
    if occurred_at is not None:
        body["occurred_at"] = occurred_at.isoformat()
    return client.post(f"/accounts/{account_id}/deposits", json=body)


def test_deposit_with_past_occurred_at_returns_201(client):
    asha = create_account(client)
    when = ago(days=3)
    r = deposit(client, asha, 1_000, occurred_at=when)
    assert r.status_code == 201
    assert datetime.fromisoformat(r.json()["occurred_at"]) == when


def test_balance_as_of_query_returns_historical_balance(client):
    asha = create_account(client)
    deposit(client, asha, 1_000, occurred_at=ago(days=3))
    deposit(client, asha, 500, occurred_at=ago(days=1))

    past = client.get(
        f"/accounts/{asha}/balance", params={"as_of": ago(days=2).isoformat()}
    )
    assert past.status_code == 200
    assert past.json()["amount"] == 1_000
    assert past.json()["as_of"] is not None

    current = client.get(f"/accounts/{asha}/balance")
    assert current.json()["amount"] == 1_500


def test_naive_as_of_returns_422(client):
    asha = create_account(client)
    r = client.get(f"/accounts/{asha}/balance", params={"as_of": "2026-01-01T00:00:00"})
    assert r.status_code == 422


def test_unparseable_as_of_returns_422(client):
    asha = create_account(client)
    r = client.get(f"/accounts/{asha}/balance", params={"as_of": "yesterday"})
    assert r.status_code == 422


def test_future_occurred_at_returns_422(client):
    asha = create_account(client)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    r = deposit(client, asha, 1_000, occurred_at=tomorrow)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "occurred_at_in_future"

    balance = client.get(f"/accounts/{asha}/balance")
    assert balance.json()["amount"] == 0