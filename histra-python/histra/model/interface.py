"""Backward-compat re-export — interfaces now live in ``histra.elements``."""
from histra.elements.interface_state import InterfaceState
from histra.elements.interface import Interface

__all__ = ["InterfaceState", "Interface"]
