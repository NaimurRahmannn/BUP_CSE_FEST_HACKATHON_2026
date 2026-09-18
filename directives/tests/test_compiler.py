"""
Tests for the GridWise Directive Compiler.

Covers:
 1. Valid solar_reduction compiles correctly
 2. Invalid solar factor (e.g., 0, 1.5) fails
 3. no_charge_window conversion
 4. minimum_battery_reserve conversion
 5. max_grid_window conversion
 6. no_op conversion
 7. Invalid hour fails (e.g., 24, -1)
 8. Integration with Optimizer
 9. Conflicting directives fail
10. Randomized directive validation
"""

import pytest
import random

from directives import (
    parse_and_compile, 
    DirectiveConflictError,
    InvalidHourError,
    InvalidParameterError,
    UnsupportedDirectiveError
)
from optimizer.models import DirectiveType, EnergyScenario, HourData, BatteryConfig
from optimizer import optimize_energy


# ===========================================================================
# Setup Helpers
# ===========================================================================

def _basic_scenario() -> EnergyScenario:
    """Helper for the integration test."""
    hours = [
        HourData(hour=h, demand_kwh=100, solar_kwh=50, tariff_bdt_per_kwh=10)
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


# ===========================================================================
# Test 1: Valid solar_reduction compiles correctly
# ===========================================================================

def test_valid_solar_reduction():
    raw = [{"type": "solar_reduction", "hours": [12, 13, 14], "factor": 0.5}]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.directive_type == DirectiveType.SOLAR_REDUCTION
    assert c.hours == [12, 13, 14]
    assert c.factor == 0.5


# ===========================================================================
# Test 2: Invalid solar factor fails
# ===========================================================================

def test_invalid_solar_factor():
    # Factor <= 0
    raw1 = [{"type": "solar_reduction", "hours": [12], "factor": 0}]
    with pytest.raises(InvalidParameterError):
        parse_and_compile(raw1, battery_capacity=200)

    # Factor > 1
    raw2 = [{"type": "solar_reduction", "hours": [12], "factor": 1.5}]
    with pytest.raises(InvalidParameterError):
        parse_and_compile(raw2, battery_capacity=200)


# ===========================================================================
# Test 3: no_charge_window conversion
# ===========================================================================

def test_no_charge_window_conversion():
    raw = [{"type": "no_charge_window", "hours": [18, 19, 20]}]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.directive_type == DirectiveType.NO_CHARGE_WINDOW
    assert c.hours == [18, 19, 20]
    # No extra parameters should be set
    assert c.factor is None
    assert c.minimum_energy_kwh is None


# ===========================================================================
# Test 4: minimum_battery_reserve conversion
# ===========================================================================

def test_minimum_battery_reserve_conversion():
    raw = [{"type": "minimum_battery_reserve", "hours": [20, 21], "minimum_energy_kwh": 150.5}]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE
    assert c.hours == [20, 21]
    assert c.minimum_energy_kwh == 150.5


# ===========================================================================
# Test 5: max_grid_window conversion
# ===========================================================================

def test_max_grid_window_conversion():
    raw = [{"type": "max_grid_window", "hours": [0, 1], "max_grid_kwh": 55.5}]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.directive_type == DirectiveType.MAX_GRID_WINDOW
    assert c.hours == [0, 1]
    assert c.max_grid_kwh == 55.5


# ===========================================================================
# Test 6: no_op conversion
# ===========================================================================

def test_no_op_conversion():
    raw = [{"type": "no_op"}]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.directive_type == DirectiveType.NO_OP
    # No effect on optimizer


# ===========================================================================
# Test 7: Invalid hour fails
# ===========================================================================

def test_invalid_hours():
    # Hour > 23
    with pytest.raises(InvalidHourError):
        parse_and_compile([{"type": "no_charge_window", "hours": [24]}], 200)
    
    # Hour < 0
    with pytest.raises(InvalidHourError):
        parse_and_compile([{"type": "no_charge_window", "hours": [-1]}], 200)

    # Duplicate hours
    with pytest.raises(InvalidHourError):
        parse_and_compile([{"type": "no_charge_window", "hours": [12, 12]}], 200)


# ===========================================================================
# Test 8: Directive + optimizer integration
# ===========================================================================

def test_directive_optimizer_integration():
    scenario = _basic_scenario()
    
    # Baseline: no directives
    result_baseline = optimize_energy(scenario)
    assert result_baseline.success
    
    # Integration: compile raw directive and pass to optimizer
    raw = [{"type": "solar_reduction", "hours": [12, 13, 14], "factor": 0.1}]
    constraints = parse_and_compile(raw, battery_capacity=scenario.battery.capacity_kwh)
    
    result_constrained = optimize_energy(scenario, directives=constraints)
    assert result_constrained.success
    
    # Because solar is reduced, total grid usage should increase
    assert result_constrained.total_grid_kwh > result_baseline.total_grid_kwh


# ===========================================================================
# Test 9: Conflicting directives
# ===========================================================================

def test_conflicting_directives_fail():
    # Minimum reserve > battery capacity (explicit conflict check)
    raw = [{"type": "minimum_battery_reserve", "hours": [12], "minimum_energy_kwh": 250}]
    
    with pytest.raises(DirectiveConflictError, match="exceeds battery capacity"):
        parse_and_compile(raw, battery_capacity=200)


# ===========================================================================
# Test 10: Randomized directive validation
# ===========================================================================

@pytest.mark.parametrize("seed", range(5))
def test_randomized_directive_validation(seed: int):
    rng = random.Random(seed)
    
    # We will generate a list of valid random directives and compile them
    raw_directives = []
    num_directives = rng.randint(1, 5)
    
    for _ in range(num_directives):
        dtype = rng.choice([
            "solar_reduction", "minimum_battery_reserve", 
            "no_charge_window", "no_discharge_window", "max_grid_window", "no_op"
        ])
        
        # Pick 1-3 random unique hours
        h_count = rng.randint(1, 3)
        hours = sorted(rng.sample(range(24), h_count))
        
        d = {"type": dtype}
        if dtype != "no_op":
            d["hours"] = hours
            
        if dtype == "solar_reduction":
            d["factor"] = round(rng.uniform(0.1, 1.0), 2)
        elif dtype == "minimum_battery_reserve":
            d["minimum_energy_kwh"] = round(rng.uniform(0, 200), 2)
        elif dtype == "max_grid_window":
            d["max_grid_kwh"] = round(rng.uniform(0, 100), 2)
            
        raw_directives.append(d)
        
    # As long as capacity >= 200 (since we cap minimum_energy_kwh at 200),
    # this should compile successfully without raising ValidationError
    # or DirectiveValidationError.
    constraints = parse_and_compile(raw_directives, battery_capacity=200.0)
    assert len(constraints) == num_directives


# ===========================================================================
# Hardening Tests
# ===========================================================================

def test_metadata_preserved():
    """Test 11: DirectiveConstraint metadata is preserved."""
    raw = [{
        "type": "no_charge_window", 
        "hours": [12],
        "source_note_id": 42,
        "raw_text": "Do not charge at noon",
        "confidence": 0.95
    }]
    constraints = parse_and_compile(raw, battery_capacity=200)
    
    assert len(constraints) == 1
    c = constraints[0]
    assert c.source_note_id == 42
    assert c.raw_text == "Do not charge at noon"
    assert c.confidence == 0.95


def test_confidence_validation():
    """Test 12: Confidence validation."""
    # Valid
    raw = [{"type": "no_charge_window", "hours": [12], "confidence": 0.5}]
    parse_and_compile(raw, battery_capacity=200)  # Should not raise
    
    # Invalid
    raw_invalid = [{"type": "no_charge_window", "hours": [12], "confidence": 1.5}]
    with pytest.raises(InvalidParameterError):
        parse_and_compile(raw_invalid, battery_capacity=200)


def test_invalid_hour_exception():
    """Test 13: Invalid hour exception."""
    raw = [{"type": "solar_reduction", "hours": [25], "factor": 0.5}]
    with pytest.raises(InvalidHourError):
        parse_and_compile(raw, battery_capacity=200)


def test_invalid_parameter_exception():
    """Test 14: Invalid parameter exception."""
    raw = [{"type": "solar_reduction", "hours": [12], "factor": 2.0}]
    with pytest.raises(InvalidParameterError):
        parse_and_compile(raw, battery_capacity=200)


def test_unsupported_directive_exception():
    """Test 15: Unsupported directive exception."""
    raw = [{"type": "unknown_action"}]
    with pytest.raises(UnsupportedDirectiveError):
        parse_and_compile(raw, battery_capacity=200)

