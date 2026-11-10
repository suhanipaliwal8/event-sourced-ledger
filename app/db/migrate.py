from pathlib import Path

import psycopg

from app.db.connection import get_migration_database_url

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def apply_migrations(database_url: str | None = None) -> list[str]:
    """Apply every not-yet-applied *.sql file in /migrations, in filename order.

    All pending migrations run in ONE transaction: either all apply or none.
    Returns the list of migration names applied in this run.
    """
    database_url = database_url or get_migration_database_url()
    applied_now: list[str] = []

    with psycopg.connect(database_url) as conn:  # commits on success, rolls back on error
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        already_applied = {
            row[0] for row in conn.execute("SELECT filename FROM schema_migrations")
        }

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already_applied:
                continue
            # No parameters passed, so psycopg lets us run a multi-statement script.
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
            )
            applied_now.append(path.name)

    return applied_now


if __name__ == "__main__":
    applied = apply_migrations()
    if applied:
        print("Applied:", ", ".join(applied))
    else:
        print("Database is up to date.")