from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Dict
from histra.springs.base import Spring


_SPRING_REGISTRY: Dict[str, type] = {}


def _register_spring(type_of: str):
    """Decorator that registers a Spring subclass for a given *TypeOf* value."""

    def wrapper(cls):
        _SPRING_REGISTRY[type_of] = cls
        return cls

    return wrapper


def spring_from_xml(elem: ET.Element) -> Spring:
    """Convenience wrapper — calls ``Spring.from_xml``."""
    return Spring.from_xml(elem)
