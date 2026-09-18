from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"
    cors_origins: str = "http://localhost:5173"

    groq_api_key: str = ""
    groq_api_base: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"

    chroma_persist_dir: str = "./chroma_data"

    # Same MySQL database as the Laravel app — used by the chat agent's
    # read-only tools. Queried directly instead of calling back into the
    # Laravel API: on `php artisan serve` (single-threaded, no forking on
    # Windows) a request FastAPI makes back to Laravel would deadlock behind
    # the very request that triggered it.
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_database: str = "rapportdrive"
    db_username: str = "root"
    db_password: str = ""
    # Set true for managed MySQL providers that enforce TLS (e.g. Aiven) —
    # encrypted, not certificate-verified (no CA file needed).
    db_ssl: bool = False
    # Optional: path to the provider's CA certificate for full verification,
    # takes precedence over db_ssl above when set.
    db_ssl_ca: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
