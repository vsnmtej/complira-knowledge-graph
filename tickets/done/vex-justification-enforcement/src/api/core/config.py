"""
Cloud API configuration.

Extends complira_graph.config.Settings with cloud-specific settings:
- Redis caching
- API authentication
- Multi-tenant database routing
- Rate limiting
"""

from complira_graph.config import Settings
from pydantic import Field
from typing import Optional


class CloudSettings(Settings):
    """
    Cloud API settings extending base Settings.

    Adds cloud-specific configuration while inheriting all
    local application settings (database, API keys, etc.).
    """

    # ========== Redis Configuration ==========
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 5  # seconds
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5  # seconds

    # Cache TTL settings (seconds)
    CACHE_TTL_REFERENCE_DATA: int = 21600  # 6 hours (CVE details, NIST controls)
    CACHE_TTL_CUSTOMER_DATA: int = 3600  # 1 hour (scan sessions, findings)
    CACHE_TTL_GRAPH_TRAVERSAL: int = 1800  # 30 minutes (blast radius, attack paths)
    CACHE_TTL_AGGREGATIONS: int = 7200  # 2 hours (portfolio risk, coverage %)

    # ========== API Authentication ==========
    API_KEY_HEADER: str = "X-API-Key"
    API_KEY_MIN_LENGTH: int = 32
    API_KEY_HASH_ROUNDS: int = 12  # bcrypt rounds

    # ========== Rate Limiting ==========
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20  # Burst allowance

    # ========== Multi-Tenant Database ==========
    ARANGO_REFERENCE_DATABASE: str = "complira_reference"
    ARANGO_CUSTOMER_DATABASE_PREFIX: str = "complira_customer_"

    # Database initialization
    AUTO_CREATE_CUSTOMER_DB: bool = True
    CUSTOMER_DB_CREATION_TIMEOUT: int = 5  # seconds

    # ========== API Server Configuration ==========
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    API_RELOAD: bool = False  # Set True for development
    API_DEBUG: bool = False

    # ========== CORS Configuration ==========
    CORS_ALLOW_ORIGINS: list = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: list = Field(default_factory=lambda: ["*"])

    # ========== Performance Tuning ==========
    MAX_GRAPH_TRAVERSAL_DEPTH: int = 6
    MAX_GRAPH_TRAVERSAL_TIME: int = 30  # seconds
    MAX_REQUEST_PAYLOAD_SIZE: int = 52428800  # 50 MB (for large SBOMs)


# Global cloud settings instance
_cloud_settings: Optional[CloudSettings] = None


def load_cloud_settings() -> CloudSettings:
    """
    Load cloud settings from environment variables.

    Returns:
        CloudSettings: Cloud application settings instance

    Raises:
        ValidationError: If required environment variables are missing
    """
    global _cloud_settings
    if _cloud_settings is None:
        _cloud_settings = CloudSettings()
    return _cloud_settings


def get_cloud_settings() -> CloudSettings:
    """
    Get cached cloud settings instance.

    Returns:
        CloudSettings: Cloud application settings instance
    """
    return load_cloud_settings()
