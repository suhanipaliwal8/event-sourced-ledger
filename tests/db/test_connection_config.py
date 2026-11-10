import pytest

from app.db.connection import (
    DEFAULT_DATABASE_URL,
    get_database_url,
    get_migration_database_url,
)


def test_database_url_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:1/db")
    assert get_database_url() == "postgresql://u:p@host:1/db"


def test_development_default_is_used_when_nothing_is_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_production_requires_an_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        get_database_url()


def test_migration_url_prefers_its_own_variable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@host/db")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner@host/db")
    assert get_migration_database_url() == "postgresql://owner@host/db"