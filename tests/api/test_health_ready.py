from fastapi.testclient import TestClient

import app.main as main_module
from app.db.health import database_is_reachable
from app.main import app


def test_ready_returns_200_when_the_database_is_reachable(monkeypatch):
    monkeypatch.setattr(main_module, "database_is_reachable", lambda: True)
    r = TestClient(app).get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_ready_returns_503_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(main_module, "database_is_reachable", lambda: False)
    r = TestClient(app).get("/health/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


def test_database_is_reachable_for_the_test_database(db_url):
    assert database_is_reachable(db_url) is True


def test_database_is_not_reachable_on_a_closed_port():
    assert database_is_reachable("postgresql://ledger:x@localhost:1/none") is False