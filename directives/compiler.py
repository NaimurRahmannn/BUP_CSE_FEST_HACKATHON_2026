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
from .errors import (
    InvalidHourError,
    InvalidParameterError,
    UnsupportedDirectiveError,
    DirectiveConflictError
)
from .validator import validate_directive_set

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
            # Map Pydantic ValidationErrors to custom Phase 2.5 errors
            for err in e.errors():
                loc = err.get("loc", ())
                err_type = err.get("type", "")
                if "type" in loc or err_type == "union_tag_invalid":
                    raise UnsupportedDirectiveError(f"Unsupported directive type: {raw.get('type')}") from e
                elif "hours" in loc:
                    raise InvalidHourError(f"Invalid hours: {err.get('msg')}") from e
                elif any(p in loc for p in ("factor", "minimum_energy_kwh", "max_grid_kwh", "confidence")):
                    raise InvalidParameterError(f"Invalid parameter in {loc}: {err.get('msg')}") from e
            
            # Fallback for other schema errors
            raise InvalidParameterError(f"Invalid directive schema: {e}") from e

    # 2. Validate conflicts
    validate_directive_set(parsed_directives, battery_capacity)

    # 3. Compile to optimizer constraints
    constraints: list[DirectiveConstraint] = []
    for d in parsed_directives:
        # Common metadata
        base_kwargs = {
            "hours": getattr(d, "hours", []),
            "source_note_id": d.source_note_id,
            "raw_text": d.raw_text,
            "confidence": d.confidence,
        }
        
        if d.type == "solar_reduction":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.SOLAR_REDUCTION,
                    factor=d.factor,
                    **base_kwargs
                )
            )
        elif d.type == "minimum_battery_reserve":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.MINIMUM_BATTERY_RESERVE,
                    minimum_energy_kwh=d.minimum_energy_kwh,
                    **base_kwargs
                )
            )
        elif d.type == "no_charge_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_CHARGE_WINDOW,
                    **base_kwargs
                )
            )
        elif d.type == "no_discharge_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
                    **base_kwargs
                )
            )
        elif d.type == "max_grid_window":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.MAX_GRID_WINDOW,
                    max_grid_kwh=d.max_grid_kwh,
                    **base_kwargs
                )
            )
        elif d.type == "no_op":
            constraints.append(
                DirectiveConstraint(
                    directive_type=DirectiveType.NO_OP,
                    **base_kwargs
                )
            )

    return constraints
