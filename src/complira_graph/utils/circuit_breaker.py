"""
Circuit breaker implementation for unreliable external services.

Used to prevent cascading failures when external APIs (like NVD) become unavailable.

Circuit States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests immediately fail
- HALF_OPEN: Recovery attempt after timeout, testing if service recovered

Example:
    @circuit_breaker(failure_threshold=5, recovery_timeout=1800, service_name="nvd")
    def fetch_nvd_data():
        response = httpx.get("https://services.nvd.nist.gov/...")
        return response.json()
"""

from enum import Enum
from functools import wraps
from datetime import datetime, timedelta
import threading
from typing import Callable, Dict
import structlog

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = 0      # Normal operation
    OPEN = 1        # Failures exceeded threshold, reject requests
    HALF_OPEN = 2   # Recovery attempt in progress


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open and requests are rejected."""
    pass


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.

    Monitors failure rate and opens circuit when threshold is exceeded.
    After recovery timeout, enters half-open state to test if service recovered.
    """

    def __init__(self, failure_threshold: int, recovery_timeout: int, service_name: str):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            service_name: Name of the service for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.service_name = service_name
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitState.CLOSED
        self.lock = threading.Lock()

        logger.info(
            "Circuit breaker initialized",
            service=service_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result if successful

        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Original exception from function if circuit is closed
        """
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker entering half-open state", service=self.service_name)
                else:
                    logger.warning(
                        "Circuit breaker is open, request rejected",
                        service=self.service_name,
                        failure_count=self.failure_count,
                        last_failure=self.last_failure_time,
                    )
                    raise CircuitBreakerOpen(
                        f"Circuit breaker open for {self.service_name}. "
                        f"Failures: {self.failure_count}, "
                        f"Will retry after: {self.last_failure_time + timedelta(seconds=self.recovery_timeout)}"
                    )

        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_recovery(self) -> bool:
        """
        Check if enough time has passed for recovery attempt.

        Returns:
            bool: True if recovery should be attempted
        """
        if not self.last_failure_time:
            return False

        time_since_failure = datetime.now() - self.last_failure_time
        should_recover = time_since_failure > timedelta(seconds=self.recovery_timeout)

        if should_recover:
            logger.info(
                "Circuit breaker recovery timeout elapsed",
                service=self.service_name,
                time_since_failure=time_since_failure.total_seconds(),
            )

        return should_recover

    def _on_success(self):
        """Reset failure count on successful request."""
        with self.lock:
            previous_state = self.state
            self.failure_count = 0
            self.state = CircuitState.CLOSED

            if previous_state != CircuitState.CLOSED:
                logger.info(
                    "Circuit breaker closed (service recovered)",
                    service=self.service_name,
                )

    def _on_failure(self):
        """Increment failure count and open circuit if threshold exceeded."""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            logger.warning(
                "Circuit breaker recorded failure",
                service=self.service_name,
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

            if self.failure_count >= self.failure_threshold:
                previous_state = self.state
                self.state = CircuitState.OPEN

                if previous_state != CircuitState.OPEN:
                    logger.error(
                        "Circuit breaker opened (failure threshold exceeded)",
                        service=self.service_name,
                        failure_count=self.failure_count,
                        threshold=self.failure_threshold,
                        recovery_timeout_seconds=self.recovery_timeout,
                    )

    def reset(self):
        """Manually reset circuit breaker to closed state."""
        with self.lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            self.last_failure_time = None
            logger.info("Circuit breaker manually reset", service=self.service_name)

    @property
    def is_open(self) -> bool:
        """Check if circuit is currently open."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is in half-open state."""
        return self.state == CircuitState.HALF_OPEN


# Global registry for circuit breakers per service
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(service_name: str, failure_threshold: int = 5, recovery_timeout: int = 1800) -> CircuitBreaker:
    """
    Get or create circuit breaker for a service.

    Circuit breakers are cached globally per service name.

    Args:
        service_name: Unique service identifier
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before recovery attempt

    Returns:
        CircuitBreaker: Circuit breaker instance for the service
    """
    with _registry_lock:
        if service_name not in _circuit_breakers:
            _circuit_breakers[service_name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                service_name=service_name,
            )
        return _circuit_breakers[service_name]


def circuit_breaker(failure_threshold: int = 5, recovery_timeout: int = 1800, service_name: str = "default"):
    """
    Decorator for applying circuit breaker to a function.

    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before recovery attempt
        service_name: Unique service identifier

    Returns:
        Decorated function with circuit breaker protection

    Example:
        @circuit_breaker(failure_threshold=5, recovery_timeout=1800, service_name="nvd")
        def fetch_nvd_data():
            response = httpx.get("https://services.nvd.nist.gov/...")
            return response.json()
    """
    def decorator(func: Callable):
        cb = get_circuit_breaker(service_name, failure_threshold, recovery_timeout)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)

        return wrapper
    return decorator
