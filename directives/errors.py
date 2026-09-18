"""
GridWise Directive Compiler — Structured Errors

Custom exceptions for robust error handling in Phase 2.5+.
"""

from __future__ import annotations


class DirectiveError(Exception):
    """Base class for all directive compiler errors."""
    pass


class InvalidDirectiveTypeError(DirectiveError, ValueError):
    """Raised when an unknown or unsupported directive type is encountered."""
    pass


class InvalidParameterError(DirectiveError, ValueError):
    """Raised when a parameter is missing or violates schema constraints (e.g., negative limits)."""
    pass


class InvalidHourError(DirectiveError, ValueError):
    """Raised when an hour array is invalid (e.g., hour > 23, negatives, duplicates)."""
    pass


class DirectiveConflictError(DirectiveError, ValueError):
    """Raised when basic physical conflicts are detected (e.g., reserve > capacity)."""
    pass


class UnsupportedDirectiveError(DirectiveError, ValueError):
    """Raised when the directive action cannot be recognized."""
    pass
