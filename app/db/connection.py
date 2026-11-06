import os

# Local development default only. Real secrets must never be committed;
# in CI and production the URL comes from the DATABASE_URL environment variable.
DEFAULT_DATABASE_URL = (
    "postgresql://ledger:ledger_dev_password@localhost:5432/ledger"
)


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)