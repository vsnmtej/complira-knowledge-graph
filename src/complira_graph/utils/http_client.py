"""
Resilient HTTP client with rate limiting, retries, and circuit breaker.

Provides a centralized HTTP client factory that eliminates code duplication
across 32+ ingestion agents.

Features:
- Rate limiting (requests per time period)
- Automatic retries with exponential backoff
- Circuit breaker for unreliable services
- Structured logging

Example:
    client = create_http_client("nvd", calls_per_period=50, period_seconds=30, circuit_breaker=True)
    response = client.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
    data = response.json()
"""

from dataclasses import dataclass
from functools import wraps
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ratelimit import limits, RateLimitException
import structlog

from .circuit_breaker import circuit_breaker as apply_circuit_breaker

logger = structlog.get_logger()


@dataclass
class RateLimitConfig:
    """Rate limit configuration for HTTP client."""
    calls: int           # Max calls per period
    period: int          # Period in seconds
    service_name: str    # Service name for logging and circuit breaker


@dataclass
class RetryConfig:
    """Retry configuration for HTTP client."""
    max_attempts: int = 3      # Maximum retry attempts
    min_wait: int = 2          # Minimum wait time in seconds
    max_wait: int = 10         # Maximum wait time in seconds


class ResilientHTTPClient:
    """
    HTTP client with built-in resilience patterns.

    Combines:
    - Rate limiting to respect API quotas
    - Automatic retries with exponential backoff
    - Optional circuit breaker for unreliable services
    """

    def __init__(
        self,
        rate_limit: RateLimitConfig,
        retry_config: Optional[RetryConfig] = None,
        timeout: float = 30.0,
        enable_circuit_breaker: bool = False,
        headers: Optional[dict] = None,
    ):
        """
        Initialize resilient HTTP client.

        Args:
            rate_limit: Rate limit configuration
            retry_config: Retry configuration (defaults to 3 attempts)
            timeout: Request timeout in seconds
            enable_circuit_breaker: Enable circuit breaker protection
            headers: Default headers for all requests
        """
        self.rate_limit = rate_limit
        self.retry_config = retry_config or RetryConfig()
        self.enable_circuit_breaker = enable_circuit_breaker

        # Create httpx client
        self.client = httpx.Client(
            timeout=timeout,
            headers=headers or {},
            follow_redirects=True,
        )

        logger.info(
            "HTTP client initialized",
            service=rate_limit.service_name,
            rate_limit=f"{rate_limit.calls} calls/{rate_limit.period}s",
            circuit_breaker=enable_circuit_breaker,
        )

    def _apply_decorators(self, func):
        """
        Apply rate limiting, retry, and circuit breaker decorators.

        Args:
            func: Function to decorate

        Returns:
            Decorated function
        """
        # Apply rate limiting
        func = limits(calls=self.rate_limit.calls, period=self.rate_limit.period)(func)

        # Apply retry with exponential backoff
        func = retry(
            stop=stop_after_attempt(self.retry_config.max_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=self.retry_config.min_wait,
                max=self.retry_config.max_wait,
            ),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )(func)

        # Apply circuit breaker if enabled
        if self.enable_circuit_breaker:
            func = apply_circuit_breaker(
                failure_threshold=5,
                recovery_timeout=1800,  # 30 minutes
                service_name=self.rate_limit.service_name,
            )(func)

        return func

    def get(self, url: str, **kwargs) -> httpx.Response:
        """
        Execute GET request with resilience patterns.

        Args:
            url: Request URL
            **kwargs: Additional arguments for httpx.get

        Returns:
            httpx.Response: HTTP response

        Raises:
            httpx.HTTPError: On HTTP error after retries exhausted
            CircuitBreakerOpen: If circuit breaker is open
        """
        @self._apply_decorators
        def _get():
            logger.debug("GET request", url=url, service=self.rate_limit.service_name)
            response = self.client.get(url, **kwargs)
            response.raise_for_status()
            return response

        return _get()

    def post(self, url: str, **kwargs) -> httpx.Response:
        """
        Execute POST request with resilience patterns.

        Args:
            url: Request URL
            **kwargs: Additional arguments for httpx.post

        Returns:
            httpx.Response: HTTP response

        Raises:
            httpx.HTTPError: On HTTP error after retries exhausted
            CircuitBreakerOpen: If circuit breaker is open
        """
        @self._apply_decorators
        def _post():
            logger.debug("POST request", url=url, service=self.rate_limit.service_name)
            response = self.client.post(url, **kwargs)
            response.raise_for_status()
            return response

        return _post()

    def close(self):
        """Close underlying HTTP client."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def create_http_client(
    service_name: str,
    calls_per_period: int,
    period_seconds: int,
    circuit_breaker: bool = False,
    timeout: float = 30.0,
    headers: Optional[dict] = None,
    retry_config: Optional[RetryConfig] = None,
) -> ResilientHTTPClient:
    """
    Factory function to create HTTP client with sensible defaults.

    Args:
        service_name: Unique service identifier (e.g., "nvd", "github")
        calls_per_period: Maximum requests per period
        period_seconds: Rate limit period in seconds
        circuit_breaker: Enable circuit breaker protection
        timeout: Request timeout in seconds
        headers: Default headers for all requests
        retry_config: Custom retry configuration

    Returns:
        ResilientHTTPClient: Configured HTTP client

    Example:
        >>> client = create_http_client("nvd", calls_per_period=50, period_seconds=30, circuit_breaker=True)
        >>> response = client.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
        >>> data = response.json()
    """
    return ResilientHTTPClient(
        rate_limit=RateLimitConfig(
            calls=calls_per_period,
            period=period_seconds,
            service_name=service_name,
        ),
        retry_config=retry_config,
        timeout=timeout,
        enable_circuit_breaker=circuit_breaker,
        headers=headers,
    )


def create_nvd_client(api_key: str) -> ResilientHTTPClient:
    """
    Create HTTP client configured for NVD API.

    NVD rate limits:
    - Without API key: 5 requests per 30 seconds
    - With API key: 50 requests per 30 seconds

    Args:
        api_key: NVD API key

    Returns:
        ResilientHTTPClient: NVD-configured client
    """
    return create_http_client(
        service_name="nvd",
        calls_per_period=50,
        period_seconds=30,
        circuit_breaker=True,  # NVD is known to have 503 errors
        timeout=60.0,
        headers={"apiKey": api_key} if api_key else {},
    )


def create_github_client(token: str) -> ResilientHTTPClient:
    """
    Create HTTP client configured for GitHub API.

    GitHub rate limits:
    - Without token: 60 requests per hour
    - With token: 5000 requests per hour

    Args:
        token: GitHub personal access token

    Returns:
        ResilientHTTPClient: GitHub-configured client
    """
    return create_http_client(
        service_name="github",
        calls_per_period=5000,
        period_seconds=3600,  # 1 hour
        circuit_breaker=False,
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        },
    )


def create_anthropic_client(api_key: str) -> ResilientHTTPClient:
    """
    Create HTTP client configured for Anthropic API.

    Args:
        api_key: Anthropic API key

    Returns:
        ResilientHTTPClient: Anthropic-configured client
    """
    return create_http_client(
        service_name="anthropic",
        calls_per_period=50,  # Conservative default
        period_seconds=60,
        circuit_breaker=False,
        timeout=120.0,  # LLM requests can be slow
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )


def create_vulncheck_client(api_key: str, timeout: float = 30.0) -> ResilientHTTPClient:
    """
    Create HTTP client configured for VulnCheck API.

    VulnCheck rate limits:
    - Community tier: 1,000 requests per minute
    - Professional tier: 10,000 requests per minute

    Args:
        api_key: VulnCheck API key (Bearer token)
        timeout: Request timeout in seconds (default: 30s, streaming endpoints may need 120s)

    Returns:
        ResilientHTTPClient: VulnCheck-configured client

    Example:
        >>> client = create_vulncheck_client(api_key="vulncheck_...")
        >>> response = client.get("https://api.vulncheck.com/v3/backup/vulncheck-kev")
        >>> data = response.json()
    """
    return create_http_client(
        service_name="vulncheck",
        calls_per_period=1000,  # Community tier: 1,000 req/min
        period_seconds=60,
        circuit_breaker=False,  # VulnCheck API is reliable
        timeout=timeout,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
