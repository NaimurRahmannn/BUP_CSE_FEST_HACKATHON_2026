"""
GridWise Directive Compiler

Translates validated LLM-generated directives into constraints
that the optimization engine can natively consume.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import TypeAdapter, ValidationError

from optimizer.models import DirectiveConstraint, DirectiveType

from .models import DirectiveModel
from .validator import DirectiveValidationError, validate_directive_set

# Pydantic TypeAdapter for parsing raw dicts into the discriminated union
_directive_adapter = TypeAdapter(DirectiveModel)


def parse_and_compile(
    raw_directives: Sequence[dict[str, Any]],
    battery_capacity: float
) -> list[DirectiveConstraint]:
    """Parse raw JSON dicts, validate them, and compile to solver constraints.

    Args:
        raw_directives: List of raw dictionaries representing directives.
        battery_capacity: Battery capacity (for conflict validation).

    Returns:
        List of DirectiveConstraint objects ready for the optimizer.

    Raises:
        ValueError: If a directive fails schema validation.
        DirectiveValidationError: If logical conflicts are detected.
    """
    # 1. Parse and validate schema
    parsed_directives: list[DirectiveModel] = []
    for raw in raw_directives:
        try:
            parsed = _directive_adapter.validate_python(raw)
            parsed_directives.append(parsed)
        except ValidationError as e:
            raise ValueError(f"Invalid directive schema: {e}") from e

    # 2. Validate conflicts
    validate_directive_set(parsed_directives, battery_capacity)

    # 3. Compile to optimizer constraints
    constraints: list[DirectiveConstraint] = []
    for d in parsed_directives:
        if d.type == "solar_reduction":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.SOLAR_REDUCTION,
                    hours=d.hours,
                    factor=d.factor,
                )
            )
        elif d.type == "minimum_battery_reserve":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.MINIMUM_BATTERY_RESERVE,
                    hours=d.hours,
                    minimum_energy_kwh=d.minimum_energy_kwh,
                )
            )
        elif d.type == "no_charge_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_CHARGE_WINDOW,
                    hours=d.hours,
                )
            )
        elif d.type == "no_discharge_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
                    hours=d.hours,
                )
            )
        elif d.type == "max_grid_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.MAX_GRID_WINDOW,
                    hours=d.hours,
                    max_grid_kwh=d.max_grid_kwh,
                )
            )
        elif d.type == "no_op":
            # Valid no_op directives compile to a NO_OP constraint or can be skipped.
            # Passing it to the solver is harmless since the solver ignores NO_OP.
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_OP,
                    hours=getattr(d, "hours", []),
                )
            )

    return constraints
