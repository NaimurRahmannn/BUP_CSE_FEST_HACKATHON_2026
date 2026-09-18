"""
GridWise Energy Optimization Engine — Independent Validator

Replays a schedule hour-by-hour and checks every competition constraint
WITHOUT trusting the solver output. This is the safety layer that ensures
no invalid schedule is ever returned.

All checks use the competition tolerance of 0.01 kWh / 0.01 BDT
(Problem Statement §11.5).
"""

from __future__ import annotations

from .models import (
    BatteryAction,
    DirectiveConstraint,
    DirectiveType,
    EnergyScenario,
    HourlyPlanEntry,
    OptimizationResult,
)

# Competition tolerance for floating-point comparisons
TOLERANCE = 0.01

NUM_HOURS = 24


def _approx_eq(a: float, b: float, tol: float = TOLERANCE) -> bool:
    """Check if two values are approximately equal within tolerance."""
    return abs(a - b) <= tol


def _approx_le(a: float, b: float, tol: float = TOLERANCE) -> bool:
    """Check if a <= b within tolerance (a - b <= tol)."""
    return a - b <= tol


def _approx_ge(a: float, b: float, tol: float = TOLERANCE) -> bool:
    """Check if a >= b within tolerance (b - a <= tol)."""
    return b - a <= tol


def compute_effective_solar(
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint],
) -> list[float]:
    """Compute effective solar per hour after solar_reduction directives.

    This duplicates the logic in solver.py intentionally — the validator
    must compute this independently.
    """
    effective = [h.solar_kwh for h in scenario.hours]
    for d in directives:
        if d.directive_type == DirectiveType.SOLAR_REDUCTION:
            factor = d.factor if d.factor is not None else 1.0
            for h in d.hours:
                effective[h] = scenario.hours[h].solar_kwh * factor
    return effective


def validate(
    result: OptimizationResult,
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint] | None = None,
) -> list[str]:
    """Validate an optimization result against the scenario and constraints.

    Returns a list of violation descriptions. Empty list means the schedule
    is valid.

    Checks performed (matching Problem Statement §09 and §11):
      1. Exactly 24 hours, 0-23
      2. No negative energy values
      3. Energy balance every hour
      4. Solar usage ≤ effective solar
      5. Battery state transition correctness
      6. Battery capacity bounds
      7. Charge/discharge rate limits
      8. battery_kwh = 0 when idle
      9. End-of-day battery neutrality
     10. Directive compliance
     11. Reported totals match recalculated values
    """
    if directives is None:
        directives = []

    errors: list[str] = []
    plan = result.hourly_plan

    # ----- Check: Exactly 24 hours, 0-23 -----
    if len(plan) != NUM_HOURS:
        errors.append(f"Expected 24 hourly entries, got {len(plan)}")
        return errors  # Cannot proceed with further checks

    hours_present = sorted(entry.hour for entry in plan)
    if hours_present != list(range(NUM_HOURS)):
        errors.append(f"Hours must be 0-23, got {hours_present}")
        return errors

    # Sort plan by hour for sequential processing
    plan_sorted = sorted(plan, key=lambda e: e.hour)

    # ----- Compute effective solar -----
    effective_solar = compute_effective_solar(scenario, directives)

    # ----- Build directive lookup tables -----
    no_charge_hours: set[int] = set()
    no_discharge_hours: set[int] = set()
    reserve_overrides: dict[int, float] = {}  # hour -> minimum_energy_kwh
    grid_caps: dict[int, float] = {}  # hour -> max_grid_kwh

    for d in directives:
        if d.directive_type == DirectiveType.NO_CHARGE_WINDOW:
            no_charge_hours.update(d.hours)
        elif d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW:
            no_discharge_hours.update(d.hours)
        elif d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
            if d.minimum_energy_kwh is not None:
                for h in d.hours:
                    # Take the maximum if multiple directives affect the same hour
                    current = reserve_overrides.get(h, 0.0)
                    reserve_overrides[h] = max(current, d.minimum_energy_kwh)
        elif d.directive_type == DirectiveType.MAX_GRID_WINDOW:
            if d.max_grid_kwh is not None:
                for h in d.hours:
                    # Take the minimum if multiple directives affect the same hour
                    current = grid_caps.get(h, float("inf"))
                    grid_caps[h] = min(current, d.max_grid_kwh)

    bat = scenario.battery
    battery_energy_before = bat.initial_energy_kwh

    total_grid_recalc = 0.0
    total_cost_recalc = 0.0
    peak_grid_recalc = 0.0

    for entry in plan_sorted:
        h = entry.hour
        hour_data = scenario.hours[h]

        # ----- Check: No negative values -----
        if entry.grid_kwh < -TOLERANCE:
            errors.append(f"Hour {h}: grid_kwh is negative ({entry.grid_kwh})")
        if entry.solar_used_kwh < -TOLERANCE:
            errors.append(f"Hour {h}: solar_used_kwh is negative ({entry.solar_used_kwh})")
        if entry.battery_kwh < -TOLERANCE:
            errors.append(f"Hour {h}: battery_kwh is negative ({entry.battery_kwh})")
        if entry.battery_energy_after_kwh < -TOLERANCE:
            errors.append(
                f"Hour {h}: battery_energy_after_kwh is negative "
                f"({entry.battery_energy_after_kwh})"
            )

        # ----- Check: Solar usage ≤ effective solar -----
        if not _approx_le(entry.solar_used_kwh, effective_solar[h]):
            errors.append(
                f"Hour {h}: solar_used_kwh ({entry.solar_used_kwh}) "
                f"exceeds effective solar ({effective_solar[h]})"
            )

        # ----- Determine charge and discharge amounts -----
        charge_kwh = 0.0
        discharge_kwh = 0.0
        if entry.battery_action == BatteryAction.CHARGE:
            charge_kwh = entry.battery_kwh
        elif entry.battery_action == BatteryAction.DISCHARGE:
            discharge_kwh = entry.battery_kwh
        elif entry.battery_action == BatteryAction.IDLE:
            # battery_kwh must be 0 when idle
            if not _approx_eq(entry.battery_kwh, 0.0):
                errors.append(
                    f"Hour {h}: battery_kwh must be 0 when idle, "
                    f"got {entry.battery_kwh}"
                )

        # ----- Check: Energy balance -----
        # grid + solar_used + discharge = demand + charge
        lhs = entry.grid_kwh + entry.solar_used_kwh + discharge_kwh
        rhs = hour_data.demand_kwh + charge_kwh
        if not _approx_eq(lhs, rhs):
            errors.append(
                f"Hour {h}: energy balance violated: "
                f"grid({entry.grid_kwh}) + solar({entry.solar_used_kwh}) "
                f"+ discharge({discharge_kwh}) = {lhs} != "
                f"demand({hour_data.demand_kwh}) + charge({charge_kwh}) = {rhs}"
            )

        # ----- Check: Battery state transition -----
        expected_energy = battery_energy_before + charge_kwh - discharge_kwh
        if not _approx_eq(entry.battery_energy_after_kwh, expected_energy):
            errors.append(
                f"Hour {h}: battery transition invalid: "
                f"before({battery_energy_before}) + charge({charge_kwh}) "
                f"- discharge({discharge_kwh}) = {expected_energy}, "
                f"but reported {entry.battery_energy_after_kwh}"
            )

        # ----- Check: Battery capacity bounds -----
        # Active minimum = max(base minimum, any directive reserve)
        active_min = bat.minimum_energy_kwh
        if h in reserve_overrides:
            active_min = max(active_min, reserve_overrides[h])

        if not _approx_ge(entry.battery_energy_after_kwh, active_min):
            errors.append(
                f"Hour {h}: battery energy ({entry.battery_energy_after_kwh}) "
                f"below minimum ({active_min})"
            )

        if not _approx_le(entry.battery_energy_after_kwh, bat.capacity_kwh):
            errors.append(
                f"Hour {h}: battery energy ({entry.battery_energy_after_kwh}) "
                f"exceeds capacity ({bat.capacity_kwh})"
            )

        # ----- Check: Charge/discharge rate limits -----
        if not _approx_le(charge_kwh, bat.max_charge_kwh_per_hour):
            errors.append(
                f"Hour {h}: charge ({charge_kwh}) exceeds max rate "
                f"({bat.max_charge_kwh_per_hour})"
            )
        if not _approx_le(discharge_kwh, bat.max_discharge_kwh_per_hour):
            errors.append(
                f"Hour {h}: discharge ({discharge_kwh}) exceeds max rate "
                f"({bat.max_discharge_kwh_per_hour})"
            )

        # ----- Check: Directive constraints -----
        if h in no_charge_hours and not _approx_eq(charge_kwh, 0.0):
            errors.append(
                f"Hour {h}: no_charge_window violated, "
                f"charge = {charge_kwh}"
            )

        if h in no_discharge_hours and not _approx_eq(discharge_kwh, 0.0):
            errors.append(
                f"Hour {h}: no_discharge_window violated, "
                f"discharge = {discharge_kwh}"
            )

        if h in grid_caps:
            if not _approx_le(entry.grid_kwh, grid_caps[h]):
                errors.append(
                    f"Hour {h}: max_grid_window violated, "
                    f"grid = {entry.grid_kwh}, cap = {grid_caps[h]}"
                )

        # Accumulate totals
        total_grid_recalc += entry.grid_kwh
        total_cost_recalc += entry.grid_kwh * hour_data.tariff_bdt_per_kwh
        peak_grid_recalc = max(peak_grid_recalc, entry.grid_kwh)

        # Advance battery state
        battery_energy_before = entry.battery_energy_after_kwh

    # ----- Check: End-of-day battery neutrality -----
    final_energy = plan_sorted[-1].battery_energy_after_kwh
    if not _approx_eq(final_energy, bat.initial_energy_kwh):
        errors.append(
            f"End-of-day battery energy ({final_energy}) "
            f"!= initial energy ({bat.initial_energy_kwh})"
        )

    # ----- Check: Reported totals match recalculated -----
    if not _approx_eq(result.total_grid_kwh, total_grid_recalc):
        errors.append(
            f"total_grid_kwh mismatch: reported {result.total_grid_kwh}, "
            f"recalculated {total_grid_recalc}"
        )

    if not _approx_eq(result.total_cost_bdt, total_cost_recalc):
        errors.append(
            f"total_cost_bdt mismatch: reported {result.total_cost_bdt}, "
            f"recalculated {total_cost_recalc}"
        )

    if not _approx_eq(result.peak_grid_kwh, peak_grid_recalc):
        errors.append(
            f"peak_grid_kwh mismatch: reported {result.peak_grid_kwh}, "
            f"recalculated {peak_grid_recalc}"
        )

    return errors


def validate_and_update(
    result: OptimizationResult,
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint] | None = None,
) -> OptimizationResult:
    """Validate the result and update its validation fields in-place.

    Returns the same result object with validation_passed and
    validation_errors populated.
    """
    errors = validate(result, scenario, directives)
    result.validation_passed = len(errors) == 0
    result.validation_errors = errors
    return result
