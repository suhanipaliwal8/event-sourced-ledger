import psycopg

from app.db.connection import get_database_url


def database_is_reachable(database_url: str | None = None) -> bool:
    """True if we can connect and run a trivial query within a couple of seconds."""
    try:
        with psycopg.connect(
            database_url or get_database_url(), connect_timeout=2, autocommit=True
        ) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False