from app.core.config import Settings


def test_settings_upgrades_plain_postgresql_scheme_to_psycopg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    monkeypatch.setenv("DIRECT_DATABASE_URL", "postgresql://user:pw@direct-host/db")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://user:pw@host/db"
    assert settings.direct_database_url == "postgresql+psycopg://user:pw@direct-host/db"


def test_settings_leaves_explicit_psycopg_scheme_unchanged(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@host/db")
    monkeypatch.setenv("DIRECT_DATABASE_URL", "postgresql+psycopg://user:pw@direct-host/db")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://user:pw@host/db"
    assert settings.direct_database_url == "postgresql+psycopg://user:pw@direct-host/db"
