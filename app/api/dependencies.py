from collections.abc import Iterator

import psycopg

from app.db.connection import connect


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: one autocommit connection per request, closed afterwards.

    Everything before `yield` runs before the route; the `finally` runs after the
    response is produced, even when the route raised an error.
    """
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()