"""
GridWise Directive Compiler

Public API for compiling LLM-generated JSON into Optimization Engine constraints.

Usage:
    from directives import parse_and_compile
    
    raw_json = [{"type": "solar_reduction", "hours": [12, 13], "factor": 0.5}]
    constraints = parse_and_compile(raw_json, battery_capacity=200.0)
"""

from .compiler import parse_and_compile
from .errors import (
    DirectiveError,
    InvalidDirectiveTypeError,
    InvalidParameterError,
    InvalidHourError,
    DirectiveConflictError,
    UnsupportedDirectiveError,
)

__all__ = [
    "parse_and_compile",
    "DirectiveError",
    "InvalidDirectiveTypeError",
    "InvalidParameterError",
    "InvalidHourError",
    "DirectiveConflictError",
    "UnsupportedDirectiveError",
]
