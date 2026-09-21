"""The domain's exception hierarchy. Nothing here imports anything.

No EXPECTED_DIVERGENCES: four exception classes and no behaviour at all. A raise
that diverges from the legacy belongs to the module that raises it, and every one
is recorded there.
"""

from __future__ import annotations

__all__ = ["CustomMatrixError", "DomainError", "SpecError", "StatisticsError"]


class DomainError(Exception):
    """Base class for the domain's own errors.

    Not every exception the domain raises: :class:`~sdg1531.scheme.TransitionMatrix`
    refuses a ragged matrix with ``ValueError`` and an out-of-range
    :meth:`~sdg1531.scheme.TransitionMatrix.with_cell` with ``IndexError``, both
    stdlib, both deliberate -- a bad index into a matrix is an ordinary programming
    error and reads better as one. ``RunSpec.from_dict`` wraps the deserialization
    path, so those two reach a caller only through direct construction and through
    ``with_cell``, the app's editing path for the transition-matrix widget: an app
    layer catching ``DomainError`` around a cell edit must catch ``IndexError``
    beside it.
    """


class SpecError(DomainError):
    """A RunSpec asks for something the engine cannot build."""


class CustomMatrixError(DomainError):
    """A custom land-cover transition CSV could not be parsed."""


class StatisticsError(DomainError):
    """A statistics payload came back in a shape the decoder cannot use."""
