"""The domain's exception hierarchy. Nothing here imports anything."""

from __future__ import annotations

__all__ = ["CustomMatrixError", "DomainError", "SpecError", "StatisticsError"]


class DomainError(Exception):
    """Base class for every error the domain raises on purpose."""


class SpecError(DomainError):
    """A RunSpec asks for something the engine cannot build."""


class CustomMatrixError(DomainError):
    """A custom land-cover transition CSV could not be parsed."""


class StatisticsError(DomainError):
    """A statistics payload came back in a shape the decoder cannot use."""
