"""Application configuration via Pydantic Settings.

All configuration comes from environment variables. Loading happens once at
import time, validation happens via Pydantic, and the result is a typed
singleton that the rest of the codebase imports.

This is the 12-factor app pattern:
- Config never lives in source code (no hard-coded secrets)
- Config is identical in shape across environments (only values differ)
- Config validation fails fast at startup, not in production at 3am

Usage:
    from clintrial.config import settings
    print(settings.aws_region)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from env vars and optional .env file.

    Pydantic Settings reads from (in order of precedence):
        1. Constructor arguments (mostly used in tests)
        2. Environment variables
        3. .env file in the project root
        4. Defaults declared in this class
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Forbid extras: a typo'd env var name fails fast instead of being silently ignored
        extra="forbid",
    )

    # -------------------------------------------------------------------------
    # AWS
    # -------------------------------------------------------------------------
    aws_region: str = Field(
        default="eu-west-2",
        description="AWS region for all resources",
    )
    aws_profile: str | None = Field(
        default=None,
        description="AWS CLI profile name (None = use default credential chain)",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="Environment name — affects resource naming and verbosity",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Minimum log level to emit",
    )

    # -------------------------------------------------------------------------
    # Kinesis
    # -------------------------------------------------------------------------
    kinesis_stream_name: str = Field(
        default="clintrial-stream-dev-events",
        description="Name of the Kinesis Data Stream to produce to / consume from",
    )

    # -------------------------------------------------------------------------
    # DynamoDB
    # -------------------------------------------------------------------------
    dynamodb_table_name: str = Field(
        default="clintrial-state-dev",
        description="DynamoDB table holding patient and event state",
    )

    # -------------------------------------------------------------------------
    # S3 (cold path / audit trail)
    # -------------------------------------------------------------------------
    s3_audit_bucket: str = Field(
        default="clintrial-audit-dev-677276115158",
        description="S3 bucket for the immutable event archive",
    )

    # -------------------------------------------------------------------------
    # Cognito
    # -------------------------------------------------------------------------
    cognito_user_pool_id: str | None = Field(
        default=None,
        description="Cognito user pool ID (populated by Terraform after pool creation)",
    )
    cognito_app_client_id: str | None = Field(
        default=None,
        description="Cognito app client ID for the API",
    )

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # -------------------------------------------------------------------------
    # Producer (synthetic event generator)
    # -------------------------------------------------------------------------
    producer_rate_eps: int = Field(
        default=50,
        ge=1,
        le=10_000,
        description="Events per second the synthetic producer emits",
    )
    producer_total_events: int = Field(
        default=1_000,
        ge=0,
        description="Total events to emit before stopping (0 = run forever)",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("aws_region")
    @classmethod
    def _validate_region(cls, v: str) -> str:
        # Light-touch validation: non-empty, dashed format
        if not v or "-" not in v:
            raise ValueError(f"aws_region {v!r} doesn't look like an AWS region")
        return v

    # -------------------------------------------------------------------------
    # Computed properties
    # -------------------------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance, loaded once per process.

    Use this in modules that may be imported during testing — tests can call
    ``get_settings.cache_clear()`` to force a reload with new env vars.
    """
    return Settings()


# Convenience: most callers just want the singleton
settings = get_settings()
