from pathlib import Path


def test_env_example_exists_and_documents_every_variable():
    content = Path(".env.example").read_text(encoding="utf-8")
    for variable in (
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "APP_ENV",
        "TEST_DATABASE_URL",
    ):
        assert variable in content


def test_env_is_gitignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()