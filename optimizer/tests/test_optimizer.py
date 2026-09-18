"""
Tests for the GridWise Energy Optimization Engine (solver + integration).

Covers:
  1. Solar only — solar reduces grid consumption
  2. Battery arbitrage — charge cheap, discharge expensive
  3. Battery reserve — optimizer respects minimum reserve
  4. Impossible scenario — solver fails gracefully
  5. No battery — zero-capacity edge case
  6. Directive: no_charge_window
  7. Directive: no_discharge_window
  8. Directive: solar_reduction
  9. Directive: minimum_battery_reserve
 10. Directive: max_grid_window
 11. Competition sample SAMPLE-01 baseline (no directives)
 12. Competition sample SAMPLE-01 with solar_reduction directive
"""

from __future__ import annotations

import pytest

from optimizer import optimize_energy
from optimizer.models import (
    BatteryAction,
    BatteryConfig,
    DirectiveConstraint,
    DirectiveType,
    EnergyScenario,
    HourData,
)
from optimizer.validator import validate


# ---------------------------------------------------------------------------
# Helper: build a simple 24-hour scenario
# ---------------------------------------------------------------------------

def _make_scenario(
    demand: list[float],
    solar: list[float],
    tariff: list[float],
    battery: BatteryConfig | None = None,
) -> EnergyScenario:
    """Create an EnergyScenario from flat lists."""
    assert len(demand) == len(solar) == len(tariff) == 24
    hours = [
        HourData(hour=h, demand_kwh=demand[h], solar_kwh=solar[h],
                 tariff_bdt_per_kwh=tariff[h])
        for h in range(24)
    ]
    if battery is None:
        battery = BatteryConfig(
            capacity_kwh=100,
            initial_energy_kwh=50,
            minimum_energy_kwh=10,
            max_charge_kwh_per_hour=25,
            max_discharge_kwh_per_hour=25,
        )
    return EnergyScenario(hours=hours, battery=battery)


def _uniform_scenario(
    demand: float = 100,
    solar: float = 0,
    tariff: float = 10,
    battery: BatteryConfig | None = None,
) -> EnergyScenario:
    """Scenario with uniform values every hour (for simple tests)."""
    return _make_scenario(
        demand=[demand] * 24,
        solar=[solar] * 24,
        tariff=[tariff] * 24,
        battery=battery,
    )


# ===========================================================================
# Test 1: Solar only (no battery)
# ===========================================================================

class TestSolarOnly:
    """Solar available, battery effectively disabled (zero capacity)."""

    def test_solar_reduces_grid(self):
        """When solar is available, total grid usage should decrease."""
        no_bat = BatteryConfig(
            capacity_kwh=0.01,  # near-zero capacity
            initial_energy_kwh=0,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=0,
            max_discharge_kwh_per_hour=0,
        )
        # Without solar
        result_no_solar = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=no_bat)
        )
        # With solar (50 kWh per hour)
        result_with_solar = optimize_energy(
            _uniform_scenario(demand=100, solar=50, tariff=10, battery=no_bat)
        )

        assert result_no_solar.success
        assert result_with_solar.success
        assert result_no_solar.validation_passed
        assert result_with_solar.validation_passed

        # Solar should reduce grid consumption
        assert result_with_solar.total_grid_kwh < result_no_solar.total_grid_kwh
        # Each hour should use 50 kWh less grid
        assert abs(result_no_solar.total_grid_kwh - 2400) < 1  # 100 * 24
        assert abs(result_with_solar.total_grid_kwh - 1200) < 1  # 50 * 24


# ===========================================================================
# Test 2: Battery arbitrage
# ===========================================================================

class TestBatteryArbitrage:
    """Battery should charge during cheap hours, discharge during expensive."""

    def test_cost_reduction_with_battery(self):
        """Total cost with battery should be lower than without."""
        # Tariff: cheap (5) for first 12h, expensive (20) for last 12h
        tariff = [5.0] * 12 + [20.0] * 12
        demand = [100.0] * 24
        solar = [0.0] * 24

        no_bat = BatteryConfig(
            capacity_kwh=0.01,
            initial_energy_kwh=0,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=0,
            max_discharge_kwh_per_hour=0,
        )
        result_no_bat = optimize_energy(
            _make_scenario(demand, solar, tariff, no_bat)
        )

        big_bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        result_with_bat = optimize_energy(
            _make_scenario(demand, solar, tariff, big_bat)
        )

        assert result_no_bat.success and result_no_bat.validation_passed
        assert result_with_bat.success and result_with_bat.validation_passed

        # Battery arbitrage should reduce cost
        assert result_with_bat.total_cost_bdt < result_no_bat.total_cost_bdt

    def test_battery_charges_cheap_discharges_expensive(self):
        """Verify the battery charges during cheap hours and discharges
        during expensive hours."""
        tariff = [5.0] * 12 + [20.0] * 12
        demand = [100.0] * 24
        solar = [0.0] * 24
        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        result = optimize_energy(_make_scenario(demand, solar, tariff, bat))
        assert result.success and result.validation_passed

        # In cheap hours (0-11), we expect net charging
        cheap_charge = sum(
            e.battery_kwh for e in result.hourly_plan[:12]
            if e.battery_action == BatteryAction.CHARGE
        )
        # In expensive hours (12-23), we expect net discharging
        expensive_discharge = sum(
            e.battery_kwh for e in result.hourly_plan[12:]
            if e.battery_action == BatteryAction.DISCHARGE
        )
        assert cheap_charge > 0, "Expected charging in cheap hours"
        assert expensive_discharge > 0, "Expected discharging in expensive hours"


# ===========================================================================
# Test 3: Battery reserve
# ===========================================================================

class TestBatteryReserve:
    """Optimizer must never violate minimum battery reserve."""

    def test_minimum_reserve_respected(self):
        """Battery never goes below minimum_energy_kwh."""
        bat = BatteryConfig(
            capacity_kwh=100,
            initial_energy_kwh=50,
            minimum_energy_kwh=30,  # strict floor
            max_charge_kwh_per_hour=25,
            max_discharge_kwh_per_hour=25,
        )
        result = optimize_energy(_uniform_scenario(
            demand=100, solar=0, tariff=10, battery=bat
        ))
        assert result.success and result.validation_passed

        for entry in result.hourly_plan:
            assert entry.battery_energy_after_kwh >= 30 - 0.01, (
                f"Hour {entry.hour}: battery {entry.battery_energy_after_kwh} "
                f"below reserve 30"
            )


# ===========================================================================
# Test 4: Impossible scenario
# ===========================================================================

class TestImpossibleScenario:
    """Demand cannot be satisfied → solver should fail gracefully."""

    def test_infeasible_demand(self):
        """No grid + no solar + no battery = impossible."""
        # max_grid is bounded by demand + max_charge in solver,
        # so we create a scenario where end-of-day neutrality makes it
        # infeasible: battery must return to initial but we force
        # contradictory constraints.
        bat = BatteryConfig(
            capacity_kwh=10,
            initial_energy_kwh=5,
            minimum_energy_kwh=5,
            max_charge_kwh_per_hour=0,   # cannot charge
            max_discharge_kwh_per_hour=0, # cannot discharge
        )
        # Solar is 0, so grid must cover all demand.
        # End-of-day neutrality: battery[23] = 5, which is fine since
        # no charge/discharge happens. This is actually feasible.
        # Let's make it infeasible by adding a directive that forces
        # grid = 0 but demand > 0.
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.MAX_GRID_WINDOW,
                hours=list(range(24)),
                max_grid_kwh=0,
            )
        ]
        result = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=bat),
            directives=directives,
        )
        assert not result.success
        assert result.error_message is not None


# ===========================================================================
# Test 5: No battery (zero capacity edge case)
# ===========================================================================

class TestNoBattery:
    """Zero-capacity battery — all demand from grid + solar."""

    def test_all_demand_from_grid(self):
        no_bat = BatteryConfig(
            capacity_kwh=0.01,
            initial_energy_kwh=0,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=0,
            max_discharge_kwh_per_hour=0,
        )
        result = optimize_energy(_uniform_scenario(
            demand=100, solar=0, tariff=10, battery=no_bat
        ))
        assert result.success and result.validation_passed
        # All demand from grid
        assert abs(result.total_grid_kwh - 2400) < 1
        # All actions should be idle
        for entry in result.hourly_plan:
            assert entry.battery_action == BatteryAction.IDLE


# ===========================================================================
# Test 6: Directive — no_charge_window
# ===========================================================================

class TestNoChargeWindow:
    """no_charge_window must force charge=0 in specified hours."""

    def test_no_charging_in_window(self):
        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                hours=[2, 3, 4],
            )
        ]
        result = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=bat),
            directives=directives,
        )
        assert result.success and result.validation_passed

        for entry in result.hourly_plan:
            if entry.hour in [2, 3, 4]:
                if entry.battery_action == BatteryAction.CHARGE:
                    assert abs(entry.battery_kwh) < 0.01, (
                        f"Hour {entry.hour}: charging in no_charge_window"
                    )


# ===========================================================================
# Test 7: Directive — no_discharge_window
# ===========================================================================

class TestNoDischargeWindow:
    """no_discharge_window must force discharge=0 in specified hours."""

    def test_no_discharging_in_window(self):
        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
                hours=[18, 19, 20],
            )
        ]
        result = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=bat),
            directives=directives,
        )
        assert result.success and result.validation_passed

        for entry in result.hourly_plan:
            if entry.hour in [18, 19, 20]:
                if entry.battery_action == BatteryAction.DISCHARGE:
                    assert abs(entry.battery_kwh) < 0.01, (
                        f"Hour {entry.hour}: discharging in no_discharge_window"
                    )


# ===========================================================================
# Test 8: Directive — solar_reduction
# ===========================================================================

class TestSolarReduction:
    """solar_reduction reduces effective solar in specified hours."""

    def test_solar_reduction_increases_grid(self):
        """Reducing solar availability should increase grid usage."""
        bat = BatteryConfig(
            capacity_kwh=0.01,
            initial_energy_kwh=0,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=0,
            max_discharge_kwh_per_hour=0,
        )
        solar = [0.0] * 6 + [50.0] * 12 + [0.0] * 6  # solar noon hours

        result_no_reduction = optimize_energy(
            _make_scenario([100.0]*24, solar, [10.0]*24, bat)
        )
        result_with_reduction = optimize_energy(
            _make_scenario([100.0]*24, solar, [10.0]*24, bat),
            directives=[
                DirectiveConstraint(
                    directive_type=DirectiveType.SOLAR_REDUCTION,
                    hours=[10, 11, 12, 13],
                    factor=0.25,  # only 25% usable
                )
            ],
        )

        assert result_no_reduction.success and result_no_reduction.validation_passed
        assert result_with_reduction.success and result_with_reduction.validation_passed

        # More grid needed when solar is reduced
        assert result_with_reduction.total_grid_kwh > result_no_reduction.total_grid_kwh


# ===========================================================================
# Test 9: Directive — minimum_battery_reserve
# ===========================================================================

class TestMinimumBatteryReserve:
    """minimum_battery_reserve raises the floor in specified hours."""

    def test_reserve_respected_in_window(self):
        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=20,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.MINIMUM_BATTERY_RESERVE,
                hours=[18, 19, 20],
                minimum_energy_kwh=100,  # much higher than base 20
            )
        ]
        result = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=bat),
            directives=directives,
        )
        assert result.success and result.validation_passed

        for entry in result.hourly_plan:
            if entry.hour in [18, 19, 20]:
                assert entry.battery_energy_after_kwh >= 100 - 0.01, (
                    f"Hour {entry.hour}: battery {entry.battery_energy_after_kwh} "
                    f"below directive reserve 100"
                )


# ===========================================================================
# Test 10: Directive — max_grid_window
# ===========================================================================

class TestMaxGridWindow:
    """max_grid_window caps grid import in specified hours."""

    def test_grid_cap_respected(self):
        bat = BatteryConfig(
            capacity_kwh=200,
            initial_energy_kwh=100,
            minimum_energy_kwh=0,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.MAX_GRID_WINDOW,
                hours=[18, 19, 20],
                max_grid_kwh=80,  # cap below demand of 100
            )
        ]
        result = optimize_energy(
            _uniform_scenario(demand=100, solar=0, tariff=10, battery=bat),
            directives=directives,
        )
        assert result.success and result.validation_passed

        for entry in result.hourly_plan:
            if entry.hour in [18, 19, 20]:
                assert entry.grid_kwh <= 80 + 0.01, (
                    f"Hour {entry.hour}: grid {entry.grid_kwh} exceeds cap 80"
                )


# ===========================================================================
# Test 11: Competition SAMPLE-01 — baseline (no directives)
# ===========================================================================

class TestCompetitionSample01:
    """Test against competition SAMPLE-01 data without directives.

    Without the solar_reduction directive, the solver should find a
    lower or equal cost compared to the reference (which had reduced solar).
    """

    @pytest.fixture
    def sample01_scenario(self) -> EnergyScenario:
        """Build SAMPLE-01 scenario from competition data."""
        hours_data = [
            (0, 90, 0, 6), (1, 85, 0, 6), (2, 80, 0, 5), (3, 80, 0, 5),
            (4, 85, 0, 5), (5, 95, 0, 6), (6, 110, 5, 8), (7, 130, 20, 10),
            (8, 150, 50, 12), (9, 165, 90, 14), (10, 175, 130, 16),
            (11, 180, 160, 16), (12, 185, 180, 15), (13, 180, 170, 14),
            (14, 170, 140, 13), (15, 165, 90, 14), (16, 170, 45, 18),
            (17, 185, 10, 22), (18, 205, 0, 28), (19, 215, 0, 30),
            (20, 205, 0, 26), (21, 175, 0, 18), (22, 135, 0, 10),
            (23, 105, 0, 7),
        ]
        hours = [
            HourData(hour=h, demand_kwh=d, solar_kwh=s, tariff_bdt_per_kwh=t)
            for h, d, s, t in hours_data
        ]
        battery = BatteryConfig(
            capacity_kwh=220,
            initial_energy_kwh=110,
            minimum_energy_kwh=40,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        return EnergyScenario(hours=hours, battery=battery)

    def test_baseline_valid(self, sample01_scenario: EnergyScenario):
        """Solver produces a valid schedule for SAMPLE-01 baseline."""
        result = optimize_energy(sample01_scenario)
        assert result.success, f"Solver failed: {result.error_message}"
        assert result.validation_passed, (
            f"Validation failed: {result.validation_errors}"
        )

    def test_baseline_cost_at_most_reference(
        self, sample01_scenario: EnergyScenario
    ):
        """Without solar_reduction, cost should be ≤ reference 38365 BDT.
        The reference had solar reduction in hours 12-13, so without it
        our optimizer can use full solar and achieve lower cost."""
        result = optimize_energy(sample01_scenario)
        assert result.success and result.validation_passed
        # Reference cost with solar reduction: 38365 BDT
        assert result.total_cost_bdt <= 38365 + 0.01


# ===========================================================================
# Test 12: Competition SAMPLE-01 — with solar_reduction directive
# ===========================================================================

class TestCompetitionSample01WithDirective:
    """Test SAMPLE-01 with the solar_reduction directive applied."""

    @pytest.fixture
    def sample01_scenario(self) -> EnergyScenario:
        hours_data = [
            (0, 90, 0, 6), (1, 85, 0, 6), (2, 80, 0, 5), (3, 80, 0, 5),
            (4, 85, 0, 5), (5, 95, 0, 6), (6, 110, 5, 8), (7, 130, 20, 10),
            (8, 150, 50, 12), (9, 165, 90, 14), (10, 175, 130, 16),
            (11, 180, 160, 16), (12, 185, 180, 15), (13, 180, 170, 14),
            (14, 170, 140, 13), (15, 165, 90, 14), (16, 170, 45, 18),
            (17, 185, 10, 22), (18, 205, 0, 28), (19, 215, 0, 30),
            (20, 205, 0, 26), (21, 175, 0, 18), (22, 135, 0, 10),
            (23, 105, 0, 7),
        ]
        hours = [
            HourData(hour=h, demand_kwh=d, solar_kwh=s, tariff_bdt_per_kwh=t)
            for h, d, s, t in hours_data
        ]
        battery = BatteryConfig(
            capacity_kwh=220,
            initial_energy_kwh=110,
            minimum_energy_kwh=40,
            max_charge_kwh_per_hour=50,
            max_discharge_kwh_per_hour=50,
        )
        return EnergyScenario(hours=hours, battery=battery)

    def test_with_solar_reduction(self, sample01_scenario: EnergyScenario):
        """With solar reduction to 25% during hours 12-13, result should
        match or beat the reference cost of 38365 BDT."""
        directives = [
            DirectiveConstraint(
                directive_type=DirectiveType.SOLAR_REDUCTION,
                hours=[12, 13],
                factor=0.25,
            )
        ]
        result = optimize_energy(sample01_scenario, directives=directives)
        assert result.success, f"Solver failed: {result.error_message}"
        assert result.validation_passed, (
            f"Validation failed: {result.validation_errors}"
        )
        # Should match reference cost (38365) within tolerance
        # Our solver may find a slightly different but equally optimal schedule
        assert result.total_cost_bdt <= 38365 + 1, (
            f"Cost {result.total_cost_bdt} exceeds reference 38365"
        )
