"""
GridWise LLM Interpretation Layer — Schemas

Defines the Pydantic schema used to force the LLM into generating
structured JSON that matches the Phase 2 Directive Compiler expectations.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LLMDirectiveOutput(BaseModel):
    """The unified schema the LLM is forced to output.
    
    This flat structure is easy for the LLM to understand and populate.
    When dumped to JSON (excluding None values), it produces the exact
    discriminated union shape expected by Phase 2.
    """
    
    type: Literal[
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    ] = Field(
        ..., 
        description="The classification of the operator note."
    )
    
    hours: Optional[list[int]] = Field(
        default=None,
        description="List of affected hours in 24h format (0-23). Leave null for no_op."
    )
    
    factor: Optional[float] = Field(
        default=None,
        description="For solar_reduction: the multiplier of remaining output (e.g., 0.2 for 80% reduction)."
    )
    
    minimum_energy_kwh: Optional[float] = Field(
        default=None,
        description="For minimum_battery_reserve: the absolute minimum kWh."
    )
    
    max_grid_kwh: Optional[float] = Field(
        default=None,
        description="For max_grid_window: the maximum allowed grid import."
    )

    def to_phase2_dict(self) -> dict:
        """Converts to a dictionary suitable for directives.parse_and_compile."""
        return self.model_dump(exclude_none=True)
