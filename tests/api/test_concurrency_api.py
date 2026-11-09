from app.domain.errors import ConcurrentModificationError
from app.services import ledger_service


def test_conflict_returns_409_with_retry_code(client, monkeypatch):
    asha = client.post("/accounts", json={"name": "Asha", "currency": "INR"}).json()["id"]

    def always_conflict(conn, tx):
        raise ConcurrentModificationError("simulated conflict")

    monkeypatch.setattr(ledger_service, "_post_once", always_conflict)

    r = client.post(
        f"/accounts/{asha}/deposits", json={"amount": 100, "currency": "INR"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "concurrent_modification"