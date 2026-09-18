"""
GridWise API — Schemas

Defines the HTTP Request and Response models for the /optimize-energy endpoint.
These serve as the serialization and validation boundary between the web client
and the internal GridWise engine.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# REQUEST SCHEMAS
# ===========================================================================

class HourDataRequest(BaseModel):
    hour: int = Field(..., ge=0, le=23)
    demand_kwh: float = Field(..., ge=0)
    solar_kwh: float = Field(..., ge=0)
    tariff_bdt_per_kwh: float = Field(..., ge=0)


class BatteryRequest(BaseModel):
    capacity_kwh: float = Field(..., gt=0)
    initial_energy_kwh: float = Field(..., ge=0)
    minimum_energy_kwh: float = Field(..., ge=0)
    max_charge_kwh_per_hour: float = Field(..., gt=0)
    max_discharge_kwh_per_hour: float = Field(..., gt=0)


class OptimizeRequest(BaseModel):
    scenario_id: str
    hours: List[HourDataRequest]
    battery: BatteryRequest
    operator_notes: Optional[List[str]] = None

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: List[HourDataRequest]) -> List[HourDataRequest]:
        if len(v) != 24:
            raise ValueError(f"Exactly 24 hours required, got {len(v)}")
        # Check that we have exactly hours 0-23
        hour_indices = sorted([h.hour for h in v])
        if hour_indices != list(range(24)):
            raise ValueError("Hours must be a complete sequence from 0 to 23")
        
        # Sort hours so they are strictly sequential
        return sorted(v, key=lambda h: h.hour)


# ===========================================================================
# RESPONSE SCHEMAS
# ===========================================================================

class DirectiveInterpretationResponse(BaseModel):
    note_index: int
    applies: bool
    directive_type: str
    structured_adjustment: dict[str, Any]
    explanation: str


class HourlyPlanResponse(BaseModel):
    hour: int
    grid_kwh: float
    battery_energy_after_kwh: float
    battery_kwh: float


class SummaryResponse(BaseModel):
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str


class ValidationResponse(BaseModel):
    success: bool
    errors: List[str]


class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[DirectiveInterpretationResponse]
    hourly_plan: Optional[List[HourlyPlanResponse]] = None
    summary: Optional[SummaryResponse] = None
    validation: ValidationResponse
    
    # Metadata
    solver_status: Optional[str] = None
    optimization_time_ms: Optional[float] = None
    pipeline_version: Optional[str] = None
