"""Application configuration management using Pydantic Settings."""

from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Settings are loaded in order:
    1. Environment variables
    2. .env file (if present)
    3. Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    secret_key: str = Field(
        default="dev-secret-key-change-in-production-must-be-32-chars-min",
        min_length=32,
    )
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://forgemind:forgemind@localhost:5432/forgemind"
    )
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = Field(default=10, ge=1, le=100)

    # ARQ Worker
    arq_queue_name: str = "forgemind-tasks"
    arq_job_timeout: int = Field(default=300, ge=10)

    # OpenAI / LLM
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    embedding_dimensions: int = 1536  # text-embedding-3-small default

    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, ge=1)
    ai_rate_limit_per_minute: int = Field(default=10, ge=1)

    # Demo Data
    seed_golden_dataset: bool = True
    demo_reset_allowed: bool = True

    # Backend Server
    backend_host: str = "0.0.0.0"  # noqa: S104
    backend_port: int = Field(default=8000, ge=1, le=65535)
    backend_workers: int = Field(default=4, ge=1, le=32)

    # Authentication (WP-2.6)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_expire_minutes: int = Field(default=30, ge=1, le=1440)
    bcrypt_cost_factor: int = Field(default=12, ge=4, le=31)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Reject insecure default secret in production/staging environments."""
        import os

        env = os.environ.get("ENVIRONMENT", "development")
        insecure_default = "dev-secret-key-change-in-production-must-be-32-chars-min"
        if env in ("production", "staging") and v == insecure_default:
            raise ValueError(
                "SECRET_KEY must not use the development default in production/staging"
            )
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


# Global settings instance
settings = Settings()
