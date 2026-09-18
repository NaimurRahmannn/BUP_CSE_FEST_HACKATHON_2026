"""
GridWise Energy Optimization Engine — Data Models

Pydantic models matching the BUP CSE Fest 2026 competition schema.
These models define the input/output contract for the optimization engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DirectiveType(str, Enum):
    """Supported operator-note directive types (Problem Statement §04)."""
    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class BatteryAction(str, Enum):
    """Allowed battery actions per hour (Problem Statement §10.3)."""
    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


# ---------------------------------------------------------------------------
# Input Models
# ---------------------------------------------------------------------------

class HourData(BaseModel):
    """Single hour of energy scenario data (Problem Statement §07.2)."""
    hour: int = Field(..., ge=0, le=23)
    demand_kwh: float = Field(..., ge=0)
    solar_kwh: float = Field(..., ge=0)
    tariff_bdt_per_kwh: float = Field(..., ge=0)


class BatteryConfig(BaseModel):
    """Battery specification (Problem Statement §07.3).

    Invariants enforced:
      - All values non-negative
      - minimum_energy_kwh <= initial_energy_kwh <= capacity_kwh
    """
    capacity_kwh: float = Field(..., gt=0)
    initial_energy_kwh: float = Field(..., ge=0)
    minimum_energy_kwh: float = Field(..., ge=0)
    max_charge_kwh_per_hour: float = Field(..., ge=0)
    max_discharge_kwh_per_hour: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _check_battery_invariants(self) -> "BatteryConfig":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError(
                f"minimum_energy_kwh ({self.minimum_energy_kwh}) "
                f"must not exceed capacity_kwh ({self.capacity_kwh})"
            )
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError(
                f"initial_energy_kwh ({self.initial_energy_kwh}) "
                f"must be >= minimum_energy_kwh ({self.minimum_energy_kwh})"
            )
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError(
                f"initial_energy_kwh ({self.initial_energy_kwh}) "
                f"must be <= capacity_kwh ({self.capacity_kwh})"
            )
        return self


class DirectiveConstraint(BaseModel):
    """A structured directive constraint produced by the directive compiler.

    This is the interface between the LLM interpretation layer (Phase 2+)
    and the optimization engine (Phase 1). The solver consumes these
    constraints directly — it never sees natural language.

    Fields mirror the competition's structured_adjustment shapes
    (Problem Statement §04.1, §05.3).
    """
    directive_type: DirectiveType
    hours: list[int] = Field(default_factory=list)

    # solar_reduction: usable fraction remaining (0 to 1)
    factor: Optional[float] = Field(default=None, ge=0, le=1)

    # minimum_battery_reserve: minimum energy level (kWh)
    minimum_energy_kwh: Optional[float] = Field(default=None, ge=0)

    # max_grid_window: maximum grid import per hour (kWh)
    max_grid_kwh: Optional[float] = Field(default=None, ge=0)

    # ----- Phase 2.5 Traceability Metadata -----
    source_note_id: Optional[int] = Field(default=None, description="ID of the source operator note")
    raw_text: Optional[str] = Field(default=None, description="Original text of the operator note")
    confidence: Optional[float] = Field(default=None, description="LLM extraction confidence")

    @field_validator("hours")
    @classmethod
    def _hours_valid(cls, v: list[int]) -> list[int]:
        for h in v:
            if not (0 <= h <= 23):
                raise ValueError(f"Hour {h} out of range 0-23")
        if len(v) != len(set(v)):
            raise ValueError("Hours must be unique")
        if v != sorted(v):
            raise ValueError("Hours must be in ascending order")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_valid(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence {v} must be between 0 and 1")
        return v


class EnergyScenario(BaseModel):
    """Complete 24-hour energy scenario input.

    Contains the hourly data and battery configuration.
    Directive constraints are passed separately to the solver.
    """
    hours: list[HourData] = Field(..., min_length=24, max_length=24)
    battery: BatteryConfig

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: list[HourData]) -> list[HourData]:
        v_sorted = sorted(v, key=lambda h: h.hour)
        expected = list(range(24))
        actual = [h.hour for h in v_sorted]
        if actual != expected:
            raise ValueError(
                f"hours must contain exactly hours 0-23, got {actual}"
            )
        return v_sorted


# ---------------------------------------------------------------------------
# Output Models
# ---------------------------------------------------------------------------

class HourlyPlanEntry(BaseModel):
    """Single hour in the output plan (Problem Statement §10.3)."""
    hour: int = Field(..., ge=0, le=23)
    grid_kwh: float = Field(..., ge=0)
    solar_used_kwh: float = Field(..., ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(..., ge=0)
    battery_energy_after_kwh: float = Field(..., ge=0)


class OptimizationResult(BaseModel):
    """Full optimization result returned by the solver.

    If success is False, hourly_plan and totals may be empty/zero,
    and error_message explains why.
    """
    success: bool
    hourly_plan: list[HourlyPlanEntry] = Field(default_factory=list)
    total_grid_kwh: float = 0.0
    total_cost_bdt: float = 0.0
    peak_grid_kwh: float = 0.0
    validation_passed: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
