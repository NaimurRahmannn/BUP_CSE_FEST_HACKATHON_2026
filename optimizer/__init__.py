"""
GridWise Energy Optimization Engine

Public API for the optimization engine.

Usage:
    from optimizer import optimize_energy
    from optimizer.models import EnergyScenario, DirectiveConstraint

    result = optimize_energy(scenario, directives=[...])
"""

from __future__ import annotations

from .models import (
    DirectiveConstraint,
    EnergyScenario,
    OptimizationResult,
)
from .solver import solve
from .validator import validate_and_update


def optimize_energy(
    scenario: EnergyScenario,
    directives: list[DirectiveConstraint] | None = None,
) -> OptimizationResult:
    """Solve the energy optimization problem and validate the result.

    This is the main entry point for the optimization engine.
    It runs the CP-SAT solver, then independently validates the solution.

    Args:
        scenario: The 24-hour energy scenario.
        directives: Optional structured directive constraints.

    Returns:
        OptimizationResult with validation status populated.
        If the solver fails, returns a failure result.
        If validation fails, the result includes validation_errors.
    """
    if directives is None:
        directives = []

    # Step 1: Solve
    result = solve(scenario, directives)

    # Step 2: Validate (only if solver succeeded)
    if result.success:
        validate_and_update(result, scenario, directives)

    return result
