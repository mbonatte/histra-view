from __future__ import annotations
from typing import Any, Callable, List, Tuple, TypeVar

T = TypeVar("T")


def _attr(elem: Any, name: str, default: Any = "",
          type: Callable[[str], Any] = str) -> Any:
    """Safely extract an XML attribute with type conversion."""
    v = elem.get(name)
    if v is None:
        return default
    try:
        return type(v)
    except (ValueError, TypeError):
        return default
