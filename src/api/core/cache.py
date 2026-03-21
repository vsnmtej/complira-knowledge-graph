"""
Redis caching service.

Provides:
- ICacheService protocol (DIP)
- RedisCacheService implementation
- @cache() decorator for declarative caching
- Cache-aside pattern support
"""

from typing import Protocol, Any, Optional, Callable
from functools import wraps
import json
import hashlib
import structlog
import redis

from api.core.config import get_cloud_settings

logger = structlog.get_logger()


class ICacheService(Protocol):
    """
    Cache service abstraction (DIP).

    Allows services to depend on abstraction, not concrete Redis implementation.
    Enables easy mocking for tests.
    """

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        ...

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        ...

    def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...

    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        ...

    def flush(self) -> None:
        """Flush all cache entries."""
        ...


class RedisCacheService:
    """
    Redis implementation of ICacheService.

    Features:
    - Connection pooling
    - JSON serialization
    - Automatic key prefixing
    - Error resilience (cache failures don't break app)
    """

    def __init__(self, key_prefix: str = "complira:"):
        """
        Initialize Redis cache service.

        Args:
            key_prefix: Prefix for all cache keys (default: "complira:")
        """
        settings = get_cloud_settings()

        self.key_prefix = key_prefix
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            decode_responses=True,  # Return strings not bytes
        )

        logger.info(
            "Redis cache service initialized",
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
        )

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.key_prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Deserialized value or None if not found/error
        """
        try:
            prefixed_key = self._make_key(key)
            value = self.client.get(prefixed_key)

            if value is None:
                logger.debug("Cache miss", key=key)
                return None

            logger.debug("Cache hit", key=key)
            return json.loads(value)

        except redis.RedisError as e:
            logger.warning(
                "Redis get error (cache disabled for this request)",
                key=key,
                error=str(e),
            )
            return None

        except json.JSONDecodeError as e:
            logger.error(
                "Cache value deserialization error",
                key=key,
                error=str(e),
            )
            # Delete corrupted cache entry
            self.delete(key)
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds
        """
        try:
            prefixed_key = self._make_key(key)
            serialized = json.dumps(value)

            self.client.setex(
                name=prefixed_key,
                time=ttl,
                value=serialized,
            )

            logger.debug("Cache set", key=key, ttl=ttl)

        except redis.RedisError as e:
            logger.warning(
                "Redis set error (cache not stored, continuing)",
                key=key,
                error=str(e),
            )

        except (TypeError, ValueError) as e:
            logger.error(
                "Cache value serialization error",
                key=key,
                error=str(e),
                value_type=type(value).__name__,
            )

    def delete(self, key: str) -> None:
        """
        Delete value from cache.

        Args:
            key: Cache key
        """
        try:
            prefixed_key = self._make_key(key)
            self.client.delete(prefixed_key)
            logger.debug("Cache delete", key=key)

        except redis.RedisError as e:
            logger.warning(
                "Redis delete error",
                key=key,
                error=str(e),
            )

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            prefixed_key = self._make_key(key)
            return bool(self.client.exists(prefixed_key))

        except redis.RedisError as e:
            logger.warning(
                "Redis exists error",
                key=key,
                error=str(e),
            )
            return False

    def flush(self) -> None:
        """
        Flush all cache entries.

        WARNING: This clears the entire Redis database.
        Use with caution in production.
        """
        try:
            self.client.flushdb()
            logger.warning("Cache flushed (all keys deleted)")

        except redis.RedisError as e:
            logger.error(
                "Redis flush error",
                error=str(e),
            )


def cache(ttl: int, key_prefix: Optional[str] = None):
    """
    Declarative caching decorator.

    Caches function return value based on function name and arguments.

    Args:
        ttl: Time-to-live in seconds
        key_prefix: Optional custom key prefix (default: function name)

    Example:
        @cache(ttl=3600)  # Cache for 1 hour
        def get_cve_details(cve_id: str) -> dict:
            # Expensive database query
            return {...}

    Cache Key Format:
        {function_name}:{arg1}:{arg2}:...:{kwarg1=val1}:{kwarg2=val2}

    Note:
        - Only works with JSON-serializable return values
        - Arguments must be hashable or JSON-serializable
        - Cache failures are silent (function executes normally)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Build cache key from function name and arguments
            func_name = key_prefix or func.__name__

            # Hash arguments to create cache key
            args_str = ":".join(str(arg) for arg in args)
            kwargs_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key_parts = [func_name, args_str, kwargs_str]
            key_base = ":".join(filter(None, key_parts))

            # Create hash of key for consistent length
            key_hash = hashlib.sha256(key_base.encode()).hexdigest()[:16]
            cache_key = f"{func_name}:{key_hash}"

            # Try cache first
            cache_service = RedisCacheService()
            cached_value = cache_service.get(cache_key)

            if cached_value is not None:
                logger.debug(
                    "Cache decorator hit",
                    function=func_name,
                    cache_key=cache_key,
                )
                return cached_value

            # Cache miss - execute function
            logger.debug(
                "Cache decorator miss",
                function=func_name,
                cache_key=cache_key,
            )
            result = func(*args, **kwargs)

            # Store in cache
            cache_service.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator
