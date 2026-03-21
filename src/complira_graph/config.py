"""
Configuration management for Complira Knowledge Graph.

Uses pydantic-settings to load configuration from environment variables.
All sensitive values (API keys, passwords) should be stored in .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ========== ArangoDB Configuration ==========
    ARANGO_URL: str = "http://localhost:8529"
    ARANGO_USERNAME: str = "root"
    ARANGO_PASSWORD: str
    ARANGO_DATABASE: str = "complira_graph"
    ARANGO_MAX_CONNECTIONS: int = 10

    # ========== Anthropic API Configuration ==========
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"  # Default model (latest Haiku)
    ANTHROPIC_MODEL_HAIKU: str = "claude-haiku-4-5"  # Fast, simple tasks (L1, L5)
    ANTHROPIC_MODEL_SONNET: str = "claude-sonnet-4-5"  # Balanced (L2, L3, L7)
    ANTHROPIC_MODEL_OPUS: str = "claude-opus-4-6"  # Complex reasoning (L4, L8)
    ANTHROPIC_MAX_TOKENS: int = 4096
    ANTHROPIC_TIMEOUT: int = 60  # seconds

    # ========== NVD API Configuration ==========
    NVD_API_KEY: str
    NVD_RATE_LIMIT_CALLS: int = 50
    NVD_RATE_LIMIT_PERIOD: int = 30  # seconds
    NVD_BASE_URL: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    # ========== GitHub API Configuration ==========
    GITHUB_TOKEN: str
    GITHUB_RATE_LIMIT: int = 5000  # per hour
    GITHUB_BASE_URL: str = "https://api.github.com"

    # ========== VulnCheck API Configuration ==========
    VULNCHECK_API_KEY: Optional[str] = None
    VULNCHECK_BASE_URL: str = "https://api.vulncheck.com/v3"

    # ========== Prefect Configuration ==========
    PREFECT_API_URL: str = "http://localhost:4200"

    # ========== Monitoring Configuration ==========
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3000
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # ========== Performance Configuration ==========
    BULK_IMPORT_BATCH_SIZE: int = 10000
    MAX_CONCURRENT_AGENTS: int = 4

    # ========== LLM Cost Tracking ==========
    LLM_MONTHLY_BUDGET_USD: float = 100.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra fields in .env
    )


# Global settings instance
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    """
    Load settings from environment variables.

    Returns:
        Settings: Application settings instance

    Raises:
        ValidationError: If required environment variables are missing
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings: Application settings instance
    """
    return load_settings()
