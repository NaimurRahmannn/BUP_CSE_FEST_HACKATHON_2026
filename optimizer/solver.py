"""
GridWise Energy Optimization Engine — CP-SAT Solver

Minimizes total grid electricity cost over a 24-hour horizon subject to
energy balance, battery physics, solar limits, and operator directive
constraints using Google OR-Tools CP-SAT.

All energy values are internally scaled by SCALE_FACTOR (×100) because
CP-SAT is an integer solver. This preserves 2 decimal places, matching
the competition's 0.01 kWh / 0.01 BDT tolerance (Problem Statement §11.5).
"""

from __future__ import annotations

from ortools.sat.python import cp_model
from config import settings

from .models import (
    BatteryAction,
    DirectiveConstraint,
    DirectiveType,
    EnergyScenario,
    HourlyPlanEntry,
    OptimizationResult,
)

# Integer scaling factor: 1 unit = 0.01 kWh
SCALE_FACTOR = 100

NUM_HOURS = 24


def _scale(value: float) -> int:
    """Convert a float kWh/BDT value to scaled integer."""
    return round(value * SCALE_FACTOR)


def _descale(value: int) -> float:
    """Convert a scaled integer back to float."""
    return value / SCALE_FACTOR


def _compute_effective_solar(
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint],
) -> list[float]:
    """Compute effective solar availability per hour after solar_reduction
    directives are applied (Problem Statement §05.3).

    effective_solar[h] = original_solar[h] × factor  (for affected hours)
    """
    effective = [h.solar_kwh for h in scenario.hours]
    for d in directives:
        if d.directive_type == DirectiveType.SOLAR_REDUCTION:
            factor = d.factor if d.factor is not None else 1.0
            for h in d.hours:
                effective[h] = scenario.hours[h].solar_kwh * factor
    return effective


def solve(
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint] | None = None,
) -> OptimizationResult:
    """Solve the 24-hour energy optimization problem.

    Args:
        scenario: The energy scenario with hourly data and battery config.
        directives: Optional list of structured directive constraints
                    (from the directive compiler).

    Returns:
        OptimizationResult with the optimal schedule or failure info.
    """
    if directives is None:
        directives = []

    model = cp_model.CpModel()
    bat = scenario.battery

    # ----- Compute effective solar after directive adjustments -----
    effective_solar = _compute_effective_solar(scenario, directives)

    # ----- Scaled constants -----
    demand_s = [_scale(scenario.hours[h].demand_kwh) for h in range(NUM_HOURS)]
    solar_s = [_scale(effective_solar[h]) for h in range(NUM_HOURS)]
    tariff_s = [_scale(scenario.hours[h].tariff_bdt_per_kwh) for h in range(NUM_HOURS)]

    capacity_s = _scale(bat.capacity_kwh)
    initial_s = _scale(bat.initial_energy_kwh)
    min_energy_s = _scale(bat.minimum_energy_kwh)
    max_charge_s = _scale(bat.max_charge_kwh_per_hour)
    max_discharge_s = _scale(bat.max_discharge_kwh_per_hour)

    # ----- Decision variables -----
    grid = []       # grid import per hour
    solar_used = [] # solar consumed per hour
    charge = []     # battery charge amount per hour
    discharge = []  # battery discharge amount per hour
    battery_e = []  # battery state-of-charge at END of each hour

    # Upper bound for grid: at most demand + max_charge (cannot exceed total need)
    # This is generous but keeps the model feasible.
    max_possible_grid = max(demand_s[h] + max_charge_s for h in range(NUM_HOURS))

    for h in range(NUM_HOURS):
        grid.append(
            model.new_int_var(0, max_possible_grid, f"grid_{h}")
        )
        solar_used.append(
            model.new_int_var(0, solar_s[h], f"solar_{h}")
        )
        charge.append(
            model.new_int_var(0, max_charge_s, f"charge_{h}")
        )
        discharge.append(
            model.new_int_var(0, max_discharge_s, f"discharge_{h}")
        )
        battery_e.append(
            model.new_int_var(min_energy_s, capacity_s, f"batt_{h}")
        )

    # ----- Mutual exclusion: cannot charge and discharge simultaneously -----
    # Use boolean indicators: is_charging[h] = 1 iff charge[h] > 0
    for h in range(NUM_HOURS):
        is_charging = model.new_bool_var(f"is_charging_{h}")
        # If is_charging=0, then charge[h]=0
        model.add(charge[h] == 0).only_enforce_if(is_charging.negated())
        # If is_charging=1, then discharge[h]=0
        model.add(discharge[h] == 0).only_enforce_if(is_charging)
        # Allow charge[h]>0 only when is_charging=1 (already implied by above)

    # ----- Constraint 1: Energy balance (every hour) -----
    # grid[h] + solar_used[h] + discharge[h] = demand[h] + charge[h]
    for h in range(NUM_HOURS):
        model.add(
            grid[h] + solar_used[h] + discharge[h]
            == demand_s[h] + charge[h]
        )

    # ----- Constraint 2: Solar limit (already in variable bounds) -----
    # solar_used[h] <= solar_s[h] — enforced by variable upper bound above.

    # ----- Constraint 3: Grid non-negative — enforced by variable lower bound. -----

    # ----- Constraint 4: Battery state transition -----
    # battery_e[0] = initial_energy + charge[0] - discharge[0]
    model.add(battery_e[0] == initial_s + charge[0] - discharge[0])
    # battery_e[h] = battery_e[h-1] + charge[h] - discharge[h]
    for h in range(1, NUM_HOURS):
        model.add(
            battery_e[h] == battery_e[h - 1] + charge[h] - discharge[h]
        )

    # ----- Constraint 5: Battery capacity — enforced by variable bounds. -----

    # ----- Constraint 6 & 7: Charge/discharge rates — enforced by variable bounds. -----

    # ----- Constraint 8: Initial battery state — embedded in transition[0]. -----

    # ----- Constraint 9: End-of-day neutrality -----
    # battery_e[23] = initial_energy_kwh
    model.add(battery_e[NUM_HOURS - 1] == initial_s)

    # ----- Directive constraints -----
    for d in directives:
        if d.directive_type == DirectiveType.NO_CHARGE_WINDOW:
            for h in d.hours:
                model.add(charge[h] == 0)

        elif d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW:
            for h in d.hours:
                model.add(discharge[h] == 0)

        elif d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
            if d.minimum_energy_kwh is not None:
                reserve_s = _scale(d.minimum_energy_kwh)
                # Active minimum = max(base minimum, directive minimum)
                active_min = max(min_energy_s, reserve_s)
                for h in d.hours:
                    model.add(battery_e[h] >= active_min)

        elif d.directive_type == DirectiveType.MAX_GRID_WINDOW:
            if d.max_grid_kwh is not None:
                cap_s = _scale(d.max_grid_kwh)
                for h in d.hours:
                    model.add(grid[h] <= cap_s)

        elif d.directive_type == DirectiveType.SOLAR_REDUCTION:
            # Solar reduction is already applied via effective_solar.
            # The variable upper bounds already reflect the reduced values.
            pass

        # no_op: no changes needed

    # ----- Objective: Minimize total grid electricity cost -----
    # cost = SUM(grid[h] * tariff[h])
    # Since both are scaled by SCALE_FACTOR, the product is scaled by
    # SCALE_FACTOR². We minimize the sum directly (scaling is monotonic).
    cost_terms = []
    for h in range(NUM_HOURS):
        cost_terms.append(grid[h] * tariff_s[h])
    model.minimize(sum(cost_terms))

    # ----- Solve -----
    solver = cp_model.CpSolver()
    # Set a reasonable time limit (competition allows 30s per request)
    solver.parameters.max_time_in_seconds = float(settings.solver_timeout_seconds)
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OptimizationResult(
            success=False,
            error_message=_status_message(status),
        )

    # ----- Extract solution -----
    hourly_plan: list[HourlyPlanEntry] = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h in range(NUM_HOURS):
        g = _descale(solver.value(grid[h]))
        s = _descale(solver.value(solar_used[h]))
        ch = _descale(solver.value(charge[h]))
        dch = _descale(solver.value(discharge[h]))
        be = _descale(solver.value(battery_e[h]))

        # Determine battery action and magnitude
        if ch > 0 and dch == 0:
            action = BatteryAction.CHARGE
            bat_kwh = ch
        elif dch > 0 and ch == 0:
            action = BatteryAction.DISCHARGE
            bat_kwh = dch
        else:
            # Both zero (simultaneous charge+discharge shouldn't happen
            # in an optimal solution as it wastes energy)
            action = BatteryAction.IDLE
            bat_kwh = 0.0

        tariff = scenario.hours[h].tariff_bdt_per_kwh
        total_grid += g
        total_cost += g * tariff
        if g > peak_grid:
            peak_grid = g

        hourly_plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=round(g, 2),
            solar_used_kwh=round(s, 2),
            battery_action=action,
            battery_kwh=round(bat_kwh, 2),
            battery_energy_after_kwh=round(be, 2),
        ))

    return OptimizationResult(
        success=True,
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid, 2),
        total_cost_bdt=round(total_cost, 2),
        peak_grid_kwh=round(peak_grid, 2),
    )


def _status_message(status: int) -> str:
    """Human-readable message for CP-SAT solver status."""
    messages = {
        cp_model.INFEASIBLE: (
            "The optimization problem is infeasible. "
            "Demand cannot be satisfied with available resources "
            "and constraints."
        ),
        cp_model.MODEL_INVALID: (
            "The optimization model is invalid. "
            "This indicates a bug in constraint formulation."
        ),
        cp_model.UNKNOWN: (
            "The solver could not determine a solution "
            "within the time limit."
        ),
    }
    return messages.get(status, f"Solver returned unexpected status: {status}")
