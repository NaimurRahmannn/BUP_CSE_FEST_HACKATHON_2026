"""
GridWise Directive Compiler — Data Models

These models define the expected structure of the incoming JSON directives
produced by the LLM (Phase 3). They provide strict validation before
the directives are compiled into constraints for the optimizer (Phase 1).
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class BaseDirectiveModel(BaseModel):
    """Base class for incoming directives."""
    type: str

    # Phase 2.5 Traceability Metadata
    source_note_id: Optional[int] = None
    raw_text: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("hours", check_fields=False)
    @classmethod
    def _validate_hours(cls, v: list[int]) -> list[int]:
        for h in v:
            if not (0 <= h <= 23):
                raise ValueError(f"Hour {h} out of range 0-23")
        if len(v) != len(set(v)):
            raise ValueError("Hours must be unique")
        if v != sorted(v):
            # Normalize to ascending order
            v = sorted(v)
        return v


class SolarReductionDirective(BaseDirectiveModel):
    type: Literal["solar_reduction"]
    hours: list[int] = Field(..., min_length=1)
    factor: float = Field(..., gt=0, le=1)


class MinimumBatteryReserveDirective(BaseDirectiveModel):
    type: Literal["minimum_battery_reserve"]
    hours: list[int] = Field(..., min_length=1)
    minimum_energy_kwh: float = Field(..., ge=0)


class NoChargeWindowDirective(BaseDirectiveModel):
    type: Literal["no_charge_window"]
    hours: list[int] = Field(..., min_length=1)


class NoDischargeWindowDirective(BaseDirectiveModel):
    type: Literal["no_discharge_window"]
    hours: list[int] = Field(..., min_length=1)


class MaxGridWindowDirective(BaseDirectiveModel):
    type: Literal["max_grid_window"]
    hours: list[int] = Field(..., min_length=1)
    max_grid_kwh: float = Field(..., ge=0)


class NoOpDirective(BaseDirectiveModel):
    type: Literal["no_op"]
    # no_op doesn't strictly need hours, but if they are provided, that's fine.


# Discriminated union allows Pydantic to parse a dict into the correct specific model
# based on the "type" field.
DirectiveModel = Annotated[
    Union[
        SolarReductionDirective,
        MinimumBatteryReserveDirective,
        NoChargeWindowDirective,
        NoDischargeWindowDirective,
        MaxGridWindowDirective,
        NoOpDirective,
    ],
    Field(discriminator="type"),
]
