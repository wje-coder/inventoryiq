"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Values are sourced from environment variables (or a local .env file
    during development). No secrets are hardcoded here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "InventoryIQ Backend"
    environment: str = "development"

    postgres_user: str = "inventoryiq"
    postgres_password: str = "inventoryiq"
    postgres_db: str = "inventoryiq"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Auth / JWT ---
    # SECRET_KEY MUST be overridden via env in any non-local environment.
    # Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"
    # This default is intentionally >= 32 bytes (HS256 best practice) but is
    # still a known, published value - never rely on it outside local dev.
    secret_key: str = "insecure-dev-secret-please-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Name/path of the httpOnly cookie used to carry the refresh token.
    refresh_cookie_name: str = "refresh_token"
    # Cookies must be Secure (HTTPS-only) outside local development.
    cookie_secure: bool = False

    # --- CORS ---
    # Comma-separated list of allowed origins. Wildcard "*" cannot be used
    # together with credentialed (cookie-based) requests, so this must be
    # an explicit list in any environment that uses the refresh cookie.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # --- Dataset ingestion ---
    # Directory (inside the backend container/host) where uploaded and
    # normalized dataset files are stored. Never served directly or built
    # from user input - only referenced by DB-generated relative paths.
    dataset_storage_dir: str = "var/datasets"
    # 20 MB default. Applied before any parsing is attempted.
    max_upload_size_bytes: int = 20 * 1024 * 1024
    # Hard server-side cap on preview endpoint rows, regardless of any
    # client-requested limit.
    dataset_preview_row_limit: int = 50
    # Number of sample values captured per column for type-inference display.
    dataset_column_sample_size: int = 5

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync driver URL, used by Alembic which does not run under asyncio."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
