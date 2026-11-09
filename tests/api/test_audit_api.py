from uuid import uuid4


def create_account(client, name="Asha") -> str:
    r = client.post("/accounts", json={"name": name, "currency": "INR"})
    assert r.status_code == 201
    return r.json()["id"]


def deposit(client, account_id, amount):
    r = client.post(
        f"/accounts/{account_id}/deposits", json={"amount": amount, "currency": "INR"}
    )
    assert r.status_code == 201


def test_audit_returns_history_with_running_balance(client):
    asha = create_account(client, "Asha")
    rahul = create_account(client, "Rahul")
    deposit(client, asha, 1_000)
    r = client.post(
        "/transfers",
        json={
            "from_account_id": asha,
            "to_account_id": rahul,
            "amount": 300,
            "currency": "INR",
            "description": "rent",
        },
    )
    assert r.status_code == 201

    audit = client.get(f"/accounts/{asha}/audit")
    assert audit.status_code == 200
    body = audit.json()

    assert [line["running_balance"] for line in body["lines"]] == [1_000, 700]
    assert body["lines"][1]["counterparties"][0]["account_name"] == "Rahul"
    assert body["lines"][1]["explanation"] == "Sent 300 to Rahul (rent)"
    assert body["summary"]["closing_balance"] == 700
    assert body["summary"]["total_credits"] == 1_000
    assert body["summary"]["total_debits"] == -300
    assert body["integrity"]["ok"] is True
    assert body["next_after_version"] is None


def test_audit_of_account_without_history(client):
    asha = create_account(client)
    body = client.get(f"/accounts/{asha}/audit").json()
    assert body["lines"] == []
    assert body["summary"]["closing_balance"] == 0
    assert body["integrity"]["ok"] is True


def test_audit_of_unknown_account_returns_404(client):
    r = client.get(f"/accounts/{uuid4()}/audit")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "account_not_found"


def test_audit_pagination(client):
    asha = create_account(client)
    for _ in range(3):
        deposit(client, asha, 100)

    first = client.get(f"/accounts/{asha}/audit", params={"limit": 2}).json()
    assert len(first["lines"]) == 2
    assert first["next_after_version"] == 2

    second = client.get(
        f"/accounts/{asha}/audit",
        params={"limit": 2, "after_version": first["next_after_version"]},
    ).json()
    assert len(second["lines"]) == 1
    assert second["lines"][0]["running_balance"] == 300
    assert second["next_after_version"] is None


def test_audit_rejects_invalid_paging_parameters(client):
    asha = create_account(client)
    assert client.get(f"/accounts/{asha}/audit", params={"limit": 0}).status_code == 422
    assert client.get(f"/accounts/{asha}/audit", params={"limit": 1000}).status_code == 422
    assert client.get(f"/accounts/{asha}/audit", params={"after_version": -1}).status_code == 422