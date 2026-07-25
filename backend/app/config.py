"""Application configuration management using Pydantic Settings.

CORS origin sources:

The ``cors_origins`` field is declared as :class:`Annotated[list[str], NoDecode]``
so the raw environment string is passed to our own ``mode="before"`` validator.
This allows the field to accept, from environment variables:
  - comma-separated origin strings: ``http://a.com,http://b.com``
  - a JSON array string: ``["http://a.com","http://b.com"]``
  - direct Python ``list[str]`` initialization.

The validator then rejects any value that does not parse as an absolute
``http://`` or ``https://`` origin (or wildcard ``*``).
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:3000"]

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
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from environment variable or direct initialization.

        Handles three input forms:
        1. String input: if it starts with '[', parse as JSON array;
           otherwise split by comma.
        2. List input: validate each item is a string.

        Every resulting origin is then validated for format:
        - Whitespace is stripped; empty entries are skipped.
        - Must start with 'http://', 'https://', or be the wildcard '*'.
        - Path component (if any) is only '' or '/'.
        - Query string and fragment are prohibited.
        """
        # Step 1: Normalize to a list of raw str candidates.
        if isinstance(v, str):
            v = cls._raw_items_from_string(v)
        elif not isinstance(v, list):
            raise ValueError(
                f"cors_origins must be a string or list, got {type(v).__name__}"
            )

        # Step 2: Validate every item and format-check the origin.
        return cls._validate_origin_list(v)

    @classmethod
    def _raw_items_from_string(cls, raw: str) -> list:
        """Convert a string env value to a list of raw items.

        - Blank string → [].
        - Starts with '[' → JSON array parse (must be a JSON list of items).
        - Otherwise → split on comma.
        """
        stripped = raw.strip()
        if not stripped:
            return []

        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON array for cors_origins: {e}"
                ) from e
            if not isinstance(parsed, list):
                raise ValueError(
                    f"JSON value must be an array, got {type(parsed).__name__}"
                )
            return parsed

        return stripped.split(",")

    @classmethod
    def _validate_origin_list(cls, items: list) -> list[str]:
        """Validate each item is a well-formed origin string."""
        result: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ValueError(
                    f"Each CORS origin must be a string, got {type(item).__name__}"
                )

            origin = item.strip()
            if not origin:
                continue

            if origin == "*":
                result.append(origin)
                continue

            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"Invalid CORS origin {origin!r}: "
                    "must start with 'http://' or 'https://'"
                )

            # urlparse handles both absolute URLs and gracefully degrades.
            parsed = urlparse(origin)

            # Reject non-root paths: path must be '' or '/'.
            if parsed.path and parsed.path != "/":
                raise ValueError(
                    f"Invalid CORS origin {origin!r}: paths are not allowed"
                )

            if parsed.query:
                raise ValueError(
                    f"Invalid CORS origin {origin!r}: query strings are not allowed"
                )

            if parsed.fragment:
                raise ValueError(
                    f"Invalid CORS origin {origin!r}: fragments are not allowed"
                )

            result.append(origin)

        return result

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
