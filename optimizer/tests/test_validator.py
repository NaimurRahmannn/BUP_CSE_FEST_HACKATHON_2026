"""
Tests for the GridWise Validation Engine.

Verifies that the validator correctly catches all categories of
constraint violations. Each test creates a known-valid schedule,
mutates it to introduce a specific violation, and asserts the
validator detects it.
"""

from __future__ import annotations

import copy

import pytest

from optimizer import optimize_energy
from optimizer.models import (
    BatteryAction,
    BatteryConfig,
    DirectiveConstraint,
    DirectiveType,
    EnergyScenario,
    HourData,
    HourlyPlanEntry,
    OptimizationResult,
)
from optimizer.validator import validate


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _base_scenario() -> EnergyScenario:
    """A simple uniform scenario for validator tests."""
    hours = [
        HourData(hour=h, demand_kwh=100, solar_kwh=0, tariff_bdt_per_kwh=10)
        for h in range(24)
    ]
    battery = BatteryConfig(
        capacity_kwh=200,
        initial_energy_kwh=100,
        minimum_energy_kwh=20,
        max_charge_kwh_per_hour=50,
        max_discharge_kwh_per_hour=50,
    )
    return EnergyScenario(hours=hours, battery=battery)


def _get_valid_result(
    scenario: EnergyScenario | None = None,
    directives: list[DirectiveConstraint] | None = None,
) -> tuple[OptimizationResult, EnergyScenario]:
    """Get a known-valid result from the solver."""
    if scenario is None:
        scenario = _base_scenario()
    result = optimize_energy(scenario, directives)
    assert result.success and result.validation_passed
    return result, scenario


# ===========================================================================
# Test: Valid schedule passes
# ===========================================================================

class TestValidSchedule:
    """A correctly solved schedule should pass validation."""

    def test_valid_passes(self):
        result, scenario = _get_valid_result()
        errors = validate(result, scenario)
        assert errors == [], f"Valid schedule failed: {errors}"


# ===========================================================================
# Test: Energy balance violation
# ===========================================================================

class TestEnergyBalanceViolation:
    """Tampering with grid_kwh should trigger energy balance error."""

    def test_grid_kwh_tampered(self):
        result, scenario = _get_valid_result()

        # Tamper: add 10 kWh to grid in hour 5
        tampered = copy.deepcopy(result)
        tampered.hourly_plan[5].grid_kwh += 10
        tampered.total_grid_kwh += 10  # keep totals "consistent"
        tampered.total_cost_bdt += 10 * 10  # 10 kWh * 10 BDT/kWh

        errors = validate(tampered, scenario)
        balance_errors = [e for e in errors if "energy balance" in e.lower()]
        assert len(balance_errors) > 0, (
            f"Expected energy balance error, got: {errors}"
        )


# ===========================================================================
# Test: Solar overuse
# ===========================================================================

class TestSolarOveruse:
    """Using more solar than available should be caught."""

    def test_solar_exceeds_available(self):
        # Scenario with some solar
        hours = [
            HourData(hour=h, demand_kwh=100, solar_kwh=50 if 8 <= h <= 16 else 0,
                     tariff_bdt_per_kwh=10)
            for h in range(24)
        ]
        battery = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=20,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        scenario = EnergyScenario(hours=hours, battery=battery)
        result, _ = _get_valid_result(scenario)

        # Tamper: use more solar than available in hour 10
        tampered = copy.deepcopy(result)
        tampered.hourly_plan[10].solar_used_kwh = 60  # max is 50

        errors = validate(tampered, scenario)
        solar_errors = [e for e in errors if "solar" in e.lower()]
        assert len(solar_errors) > 0, (
            f"Expected solar overuse error, got: {errors}"
        )


# ===========================================================================
# Test: Battery limit violation
# ===========================================================================

class TestBatteryLimitViolation:
    """Battery energy exceeding capacity should be caught."""

    def test_battery_exceeds_capacity(self):
        result, scenario = _get_valid_result()

        # Tamper: set battery energy above capacity
        tampered = copy.deepcopy(result)
        tampered.hourly_plan[5].battery_energy_after_kwh = 250  # cap is 200

        errors = validate(tampered, scenario)
        capacity_errors = [e for e in errors if "capacity" in e.lower()
                          or "exceeds" in e.lower()]
        assert len(capacity_errors) > 0, (
            f"Expected battery capacity error, got: {errors}"
        )


# ===========================================================================
# Test: End-of-day neutrality violation
# ===========================================================================

class TestEndOfDayViolation:
    """Final battery energy != initial should be caught."""

    def test_final_energy_mismatch(self):
        result, scenario = _get_valid_result()

        # Tamper: change final hour's battery energy
        tampered = copy.deepcopy(result)
        tampered.hourly_plan[23].battery_energy_after_kwh = 50  # initial is 100

        errors = validate(tampered, scenario)
        eod_errors = [e for e in errors if "end-of-day" in e.lower()
                     or "initial" in e.lower()]
        assert len(eod_errors) > 0, (
            f"Expected end-of-day error, got: {errors}"
        )


# ===========================================================================
# Test: Negative values
# ===========================================================================

class TestNegativeValues:
    """Negative energy values should be caught."""

    def test_negative_grid(self):
        result, scenario = _get_valid_result()

        tampered = copy.deepcopy(result)
        tampered.hourly_plan[3].grid_kwh = -10

        errors = validate(tampered, scenario)
        neg_errors = [e for e in errors if "negative" in e.lower()]
        assert len(neg_errors) > 0, (
            f"Expected negative value error, got: {errors}"
        )


# ===========================================================================
# Test: Idle battery_kwh non-zero
# ===========================================================================

class TestIdleBatteryNonZero:
    """battery_kwh must be 0 when battery_action is idle."""

    def test_idle_with_nonzero_kwh(self):
        result, scenario = _get_valid_result()

        # Find an idle entry and tamper it
        tampered = copy.deepcopy(result)
        for entry in tampered.hourly_plan:
            if entry.battery_action == BatteryAction.IDLE:
                entry.battery_kwh = 5.0
                break
        else:
            # If no idle entries, force one
            tampered.hourly_plan[0].battery_action = BatteryAction.IDLE
            tampered.hourly_plan[0].battery_kwh = 5.0

        errors = validate(tampered, scenario)
        idle_errors = [e for e in errors if "idle" in e.lower()]
        assert len(idle_errors) > 0, (
            f"Expected idle battery error, got: {errors}"
        )


# ===========================================================================
# Test: Directive violation — no_charge_window
# ===========================================================================

class TestNoChargeDirectiveViolation:
    """Charging during no_charge_window hours should be caught."""

    def test_charge_in_no_charge_window(self):
        result, scenario = _get_valid_result()
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                hours=[5, 6, 7],
            )
        ]

        # Tamper: force a charge action in restricted hour
        tampered = copy.deepcopy(result)
        tampered.hourly_plan[5].battery_action = BatteryAction.CHARGE
        tampered.hourly_plan[5].battery_kwh = 10

        errors = validate(tampered, scenario, directives)
        nc_errors = [e for e in errors if "no_charge" in e.lower()]
        assert len(nc_errors) > 0, (
            f"Expected no_charge_window violation, got: {errors}"
        )


# ===========================================================================
# Test: Directive violation — no_discharge_window
# ===========================================================================

class TestNoDischargeDirectiveViolation:
    """Discharging during no_discharge_window hours should be caught."""

    def test_discharge_in_no_discharge_window(self):
        result, scenario = _get_valid_result()
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
                hours=[18, 19, 20],
            )
        ]

        tampered = copy.deepcopy(result)
        tampered.hourly_plan[18].battery_action = BatteryAction.DISCHARGE
        tampered.hourly_plan[18].battery_kwh = 10

        errors = validate(tampered, scenario, directives)
        nd_errors = [e for e in errors if "no_discharge" in e.lower()]
        assert len(nd_errors) > 0, (
            f"Expected no_discharge_window violation, got: {errors}"
        )


# ===========================================================================
# Test: Directive violation — max_grid_window
# ===========================================================================

class TestMaxGridDirectiveViolation:
    """Grid usage exceeding max_grid_window should be caught."""

    def test_grid_exceeds_cap(self):
        result, scenario = _get_valid_result()
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.MAX_GRID_WINDOW,
                hours=[10, 11, 12],
                max_grid_kwh=50,
            )
        ]

        tampered = copy.deepcopy(result)
        tampered.hourly_plan[10].grid_kwh = 60  # exceeds cap of 50

        errors = validate(tampered, scenario, directives)
        mg_errors = [e for e in errors if "max_grid" in e.lower()]
        assert len(mg_errors) > 0, (
            f"Expected max_grid_window violation, got: {errors}"
        )


# ===========================================================================
# Test: Totals mismatch
# ===========================================================================

class TestTotalsMismatch:
    """Reported totals disagreeing with hourly_plan should be caught."""

    def test_total_grid_mismatch(self):
        result, scenario = _get_valid_result()

        tampered = copy.deepcopy(result)
        tampered.total_grid_kwh = result.total_grid_kwh + 100

        errors = validate(tampered, scenario)
        total_errors = [e for e in errors if "total_grid" in e.lower()]
        assert len(total_errors) > 0, (
            f"Expected total mismatch error, got: {errors}"
        )

    def test_total_cost_mismatch(self):
        result, scenario = _get_valid_result()

        tampered = copy.deepcopy(result)
        tampered.total_cost_bdt = result.total_cost_bdt + 500

        errors = validate(tampered, scenario)
        cost_errors = [e for e in errors if "total_cost" in e.lower()]
        assert len(cost_errors) > 0, (
            f"Expected cost mismatch error, got: {errors}"
        )

    def test_peak_grid_mismatch(self):
        result, scenario = _get_valid_result()

        tampered = copy.deepcopy(result)
        tampered.peak_grid_kwh = result.peak_grid_kwh + 50

        errors = validate(tampered, scenario)
        peak_errors = [e for e in errors if "peak_grid" in e.lower()]
        assert len(peak_errors) > 0, (
            f"Expected peak mismatch error, got: {errors}"
        )


# ===========================================================================
# Test: Randomized — validator catches invalid schedules
# ===========================================================================

class TestRandomizedValidation:
    """Generate scenarios and verify validator catches mutations."""

    @pytest.mark.parametrize("seed", range(5))
    def test_random_mutation_detected(self, seed: int):
        """Solve a scenario, mutate one value, check validator catches it."""
        import random
        rng = random.Random(seed)

        # Random demand, tariff
        demand = [rng.uniform(50, 200) for _ in range(24)]
        solar = [rng.uniform(0, 50) if 6 <= h <= 18 else 0 for h in range(24)]
        tariff = [rng.uniform(5, 30) for _ in range(24)]

        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=20,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        hours = [
            HourData(hour=h, demand_kwh=demand[h], solar_kwh=solar[h],
                     tariff_bdt_per_kwh=tariff[h])
            for h in range(24)
        ]
        scenario = EnergyScenario(hours=hours, battery=bat)
        result = optimize_energy(scenario)
        assert result.success and result.validation_passed

        # Mutate: randomly break one value
        tampered = copy.deepcopy(result)
        target_hour = rng.randint(0, 23)
        mutation = rng.choice([
            "grid", "solar", "battery_energy", "battery_kwh"
        ])

        if mutation == "grid":
            tampered.hourly_plan[target_hour].grid_kwh += rng.uniform(5, 20)
        elif mutation == "solar":
            tampered.hourly_plan[target_hour].solar_used_kwh += rng.uniform(10, 50)
        elif mutation == "battery_energy":
            tampered.hourly_plan[target_hour].battery_energy_after_kwh += 100
        elif mutation == "battery_kwh":
            tampered.hourly_plan[target_hour].battery_kwh += rng.uniform(5, 20)

        errors = validate(tampered, scenario)
        assert len(errors) > 0, (
            f"Seed {seed}: mutation '{mutation}' at hour {target_hour} "
            f"was not detected"
        )
