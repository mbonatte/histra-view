"""Validation helpers for comparing Python outputs with original HiStrA results."""

from .modal_results import (
    ModalComparisonTolerances,
    compare_modal_result_to_csharp,
    read_csharp_modal_reference,
)

__all__ = [
    "ModalComparisonTolerances",
    "compare_modal_result_to_csharp",
    "read_csharp_modal_reference",
]
