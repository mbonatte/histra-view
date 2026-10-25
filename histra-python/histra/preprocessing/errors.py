"""Errors raised while translating a model into solver-ready topology."""


class ModelPreparationError(RuntimeError):
    """Raised when an HRX uses an unsupported or invalid preparation feature."""
