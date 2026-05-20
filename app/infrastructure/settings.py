from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App-facing DB connection (FastAPI -> PgBouncer on localhost)
    app_postgres_host: str = "localhost"
    app_postgres_port: int = 6432
    app_postgres_user: str
    app_postgres_password: str
    app_postgres_db: str

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Alembic
    alembic_shared_db: str = "aton_clients"
    alembic_template_db: str = "client_template"

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if not v or len(v) < 32 or v == "dev-secret-change-in-production":
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters and not a placeholder")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
