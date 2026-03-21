"""
Common data transformation utilities.

Provides reusable transformation patterns to avoid code duplication across agents:
- Nested data extraction from JSON
- Safe date/datetime parsing
- Batching for bulk imports
- Safe field extraction with defaults
"""

from typing import Iterator, Any, Callable, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


def extract_nested_array(data: dict, path: str, default: Optional[list] = None) -> list:
    """
    Extract nested array from JSON using dot-notation path.

    Args:
        data: Source dictionary
        path: Dot-separated path (e.g., "cve.weaknesses")
        default: Default value if path not found

    Returns:
        list: Extracted array or default

    Examples:
        >>> data = {"cve": {"weaknesses": [{"value": "CWE-79"}]}}
        >>> extract_nested_array(data, "cve.weaknesses")
        [{'value': 'CWE-79'}]

        >>> extract_nested_array(data, "missing.path", default=[])
        []
    """
    if default is None:
        default = []

    if "." not in path:
        return data.get(path, default)

    keys = path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default

    return current if isinstance(current, list) else default


def safe_date_parse(date_str: str | None, default: datetime | None = None) -> datetime | None:
    """
    Parse ISO datetime string with fallback.

    Handles common formats:
    - ISO 8601 with 'Z' suffix
    - ISO 8601 with timezone offset
    - Boolean values (True/False from APIs like endoflife.date)

    Args:
        date_str: ISO datetime string, boolean, or None
        default: Default value if parsing fails

    Returns:
        datetime | None: Parsed datetime or default

    Examples:
        >>> safe_date_parse("2024-01-15T10:30:00Z")
        datetime.datetime(2024, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)

        >>> safe_date_parse("invalid", default=None)
        None

        >>> safe_date_parse(True)  # endoflife.date uses True/False for some fields
        None
    """
    if not date_str:
        return default

    # Handle non-string types (booleans, numbers, etc.)
    if not isinstance(date_str, str):
        logger.debug(
            "Date field is not a string, returning default",
            date_value=date_str,
            date_type=type(date_str).__name__,
        )
        return default

    try:
        # Replace 'Z' with '+00:00' for fromisoformat compatibility
        normalized = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError) as e:
        logger.debug(
            "Failed to parse date",
            date_str=date_str,
            error=str(e),
        )
        return default


def batch_iterator(items: Iterator[Any], batch_size: int = 10000) -> Iterator[list[Any]]:
    """
    Batch items for bulk import operations.

    Args:
        items: Iterator of items
        batch_size: Number of items per batch

    Yields:
        list: Batches of items

    Example:
        >>> items = ({"_key": f"item_{i}"} for i in range(25000))
        >>> for batch in batch_iterator(items, batch_size=10000):
        ...     db.collection("test").import_bulk(batch)
        # Yields: [item_0...item_9999], [item_10000...item_19999], [item_20000...item_24999]
    """
    batch = []

    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    # Yield remaining items
    if batch:
        yield batch


def safe_extract(
    data: dict,
    key: str,
    default: Any = None,
    transform: Optional[Callable] = None
) -> Any:
    """
    Safely extract value from dictionary with optional transformation.

    Args:
        data: Source dictionary
        key: Key to extract
        default: Default value if key missing or transform fails
        transform: Optional transformation function

    Returns:
        Any: Extracted and optionally transformed value

    Examples:
        >>> data = {"score": "7.5"}
        >>> safe_extract(data, "score", default=0.0, transform=float)
        7.5

        >>> safe_extract(data, "missing", default=0.0, transform=float)
        0.0

        >>> data = {"score": "invalid"}
        >>> safe_extract(data, "score", default=0.0, transform=float)
        0.0
    """
    value = data.get(key, default)

    if transform and value is not None:
        try:
            return transform(value)
        except (ValueError, TypeError) as e:
            logger.debug(
                "Transform failed, using default",
                key=key,
                value=value,
                error=str(e),
            )
            return default

    return value


def safe_extract_nested(
    data: dict,
    path: str,
    default: Any = None,
    transform: Optional[Callable] = None
) -> Any:
    """
    Safely extract value from nested dictionary using dot-notation path.

    Args:
        data: Source dictionary
        path: Dot-separated path (e.g., "metrics.cvssMetricV31[0].cvssData.baseScore")
        default: Default value if path not found or transform fails
        transform: Optional transformation function

    Returns:
        Any: Extracted and optionally transformed value

    Examples:
        >>> data = {"metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 7.5}}]}}
        >>> safe_extract_nested(data, "metrics.cvssMetricV31.0.cvssData.baseScore", transform=float)
        7.5

        >>> safe_extract_nested(data, "missing.path", default=0.0)
        0.0
    """
    keys = path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            # Handle array indexing (e.g., "array.0.field")
            try:
                index = int(key)
                current = current[index] if index < len(current) else None
            except (ValueError, IndexError):
                return default
        else:
            return default

        if current is None:
            return default

    # Apply transformation if provided
    if transform and current is not None:
        try:
            return transform(current)
        except (ValueError, TypeError) as e:
            logger.debug(
                "Transform failed on nested extract, using default",
                path=path,
                value=current,
                error=str(e),
            )
            return default

    return current


def deduplicate_list(items: list, key: Optional[Callable] = None) -> list:
    """
    Deduplicate list while preserving order.

    Args:
        items: List to deduplicate
        key: Optional function to extract comparison key

    Returns:
        list: Deduplicated list

    Examples:
        >>> deduplicate_list([1, 2, 2, 3, 1])
        [1, 2, 3]

        >>> items = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 1, "name": "a"}]
        >>> deduplicate_list(items, key=lambda x: x["id"])
        [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]
    """
    seen = set()
    result = []

    for item in items:
        # Get comparison value
        comp_value = key(item) if key else item

        # Skip if already seen
        if comp_value in seen:
            continue

        seen.add(comp_value)
        result.append(item)

    return result


def flatten_list(nested_list: list) -> list:
    """
    Flatten a nested list structure.

    Args:
        nested_list: List potentially containing nested lists

    Returns:
        list: Flattened list

    Examples:
        >>> flatten_list([1, [2, 3], [4, [5, 6]]])
        [1, 2, 3, 4, 5, 6]
    """
    result = []

    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)

    return result


def normalize_string(value: str | None) -> str | None:
    """
    Normalize string by stripping whitespace and converting empty to None.

    Args:
        value: String to normalize

    Returns:
        str | None: Normalized string or None

    Examples:
        >>> normalize_string("  hello  ")
        'hello'

        >>> normalize_string("   ")
        None

        >>> normalize_string(None)
        None
    """
    if value is None:
        return None

    normalized = value.strip()
    return normalized if normalized else None
