"""Utils module."""

import datetime
from typing import Any, TypeVar

import pytz

EST_TIMEZONE = pytz.timezone("Canada/Eastern")

T = TypeVar("T")


def now() -> datetime.datetime:
    """Get EST localized now datetime."""
    return EST_TIMEZONE.localize(datetime.datetime.now())


def safe_get(
    data: dict[str, Any] | list[Any] | Any,
    *keys: str | int,
    default: T | None = None,
) -> Any | T | None:
    """Safely access nested dictionary/list keys and indices.

    Args:
        data: The dictionary or list to access
        *keys: Sequence of keys/indices to traverse (strings for dict keys, ints for list indices)
        default: Default value if key path doesn't exist

    Returns:
        The value at the key path, or default if not found

    Example:
        >>> data = {"a": {"b": {"c": 123}}}
        >>> safe_get(data, "a", "b", "c")
        123
        >>> safe_get(data, "a", "x", "y", default=0)
        0
        >>> data = {"items": [{"id": 1}, {"id": 2}]}
        >>> safe_get(data, "items", 0, "id")
        1
    """
    current: Any = data
    for key in keys:
        try:
            if isinstance(current, dict) and isinstance(key, str):
                if key not in current:
                    return default
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int):
                if key < 0 or key >= len(current):
                    return default
                current = current[key]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default
    return current
