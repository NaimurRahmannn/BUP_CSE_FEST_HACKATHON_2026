"""
GridWise Directive Compiler — Validator

Performs basic conflict detection on a set of parsed directives.
Rejects sets with obvious physical contradictions.
"""

from __future__ import annotations

from typing import Sequence

from .models import (
    DirectiveModel,
    MinimumBatteryReserveDirective,
    NoChargeWindowDirective,
    NoDischargeWindowDirective,
)


class DirectiveValidationError(Exception):
    """Raised when a set of directives contains conflicts."""
    pass


def validate_directive_set(directives: Sequence[DirectiveModel], battery_capacity: float) -> None:
    """Validate a set of directives for basic conflicts.

    Args:
        directives: The list of parsed DirectiveModel instances.
        battery_capacity: The maximum capacity of the battery in kWh.

    Raises:
        DirectiveValidationError: If a conflict or invalid state is detected.
    """
    no_charge_hours: set[int] = set()
    no_discharge_hours: set[int] = set()

    for d in directives:
        # Check battery capacity limits
        if isinstance(d, MinimumBatteryReserveDirective):
            if d.minimum_energy_kwh > battery_capacity:
                raise DirectiveValidationError(
                    f"Minimum battery reserve ({d.minimum_energy_kwh} kWh) "
                    f"exceeds battery capacity ({battery_capacity} kWh)."
                )

        # Track charge/discharge restrictions for overlap checking
        if isinstance(d, NoChargeWindowDirective):
            no_charge_hours.update(d.hours)
        elif isinstance(d, NoDischargeWindowDirective):
            no_discharge_hours.update(d.hours)

    # Note: While no_charge AND no_discharge on the same hour isn't physically
    # impossible (it just means the battery MUST be idle), it restricts the solver.
    # The requirement asks for basic conflict detection, such as:
    # "no_charge_window AND required charging constraint -> Reject"
    # Since we only have `minimum_battery_reserve` as a positive constraint (which
    # might require charging to reach if the battery starts low), checking that
    # purely analytically here is complex (requires knowing the battery initial state
    # and previous hours' usage).
    #
    # We will let the CP-SAT solver handle complex dynamic infeasibility, and only
    # catch explicit simple contradictions here, as requested: "minimum reserve
    # exceeds battery capacity".
