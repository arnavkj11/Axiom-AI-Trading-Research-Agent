from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env.

    Neon issues two connection strings: a pooled one (via PgBouncer) and a
    direct one. The app uses the pooled connection at runtime; Alembic uses
    the direct connection because migrations need a real session (PgBouncer's
    transaction pooling mode is incompatible with some DDL/session state).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    direct_database_url: str
    alpha_vantage_api_key: str
    voyage_ai_api_key: str
    anthropic_api_key: str
    # SEC's fair-access policy requires an identifying User-Agent (name +
    # contact email) on every EDGAR request. Defaulted so this feature
    # doesn't add another required .env entry; override via .env if needed.
    edgar_user_agent: str = "Axiom Research Platform (contact: arnavkj11@gmail.com)"
    # Origin the Next.js frontend is served from. The browser blocks the
    # frontend's calls to this API without it (different port = different
    # origin). Defaulted to the Next dev server; override via .env when the
    # frontend is served from anywhere else.
    frontend_origin: str = "http://localhost:3000"
    # Safe (slow) defaults for Voyage's free-trial-without-billing rate
    # limit (3 RPM / 10K TPM). Once a payment method is added (Tier 1: 2000
    # RPM / 8M TPM), raise these via .env — see app/filings/voyage_client.py.
    voyage_batch_size: int = 5
    voyage_min_seconds_between_requests: float = 25.0

    @field_validator("database_url", "direct_database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Neon's dashboard hands out plain "postgresql://" URLs, which
        # SQLAlchemy defaults to the psycopg2 driver. We install psycopg
        # (v3) instead, so normalize here rather than relying on everyone
        # who copies a connection string in to edit it by hand.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


settings = Settings()
