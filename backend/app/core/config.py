"""Centralized application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    app_name: str = Field(default="OmniSearch Backend", description="Display name of the application")
    app_version: str = Field(default="0.1.0", description="Semantic version string")
    environment: str = Field(default="development", description="Runtime environment: development, testing, production")
    debug: bool = Field(default=True, description="Enable debug mode")

    # Network configuration - local-first desktop application binds to 127.0.0.1
    host: str = Field(default="127.0.0.1", description="Host address for local server binding")
    port: int = Field(default=8000, description="Port number for local server binding")

    # Security & CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origin list for local frontend access",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Standard logging level")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
