"""
Tests for the GridWise LLM Interpretation Layer (Phase 3).

Covers:
 1. Clear solar reduction
 2. Battery reserve instruction
 3. No charging instruction
 4. Irrelevant note
 5. Ambiguous instruction
 6. Paraphrase handling
 7. Invalid LLM output (safe failure)
 8. End-to-end integration
"""

import json
from unittest.mock import patch

import pytest

from llm import parse_operator_note
from directives import parse_and_compile
from optimizer import optimize_energy
from optimizer.models import EnergyScenario, HourData, BatteryConfig


# ===========================================================================
# Mock Setup
# ===========================================================================
# We mock the `call_llm` function to return deterministic JSON strings
# so the tests run reliably without hitting the live Gemini API.

def mock_call_llm(return_json: dict | str):
    """Helper to create a patched context manager for call_llm."""
    if isinstance(return_json, dict):
        return_str = json.dumps(return_json)
    else:
        return_str = return_json
    return patch("llm.parser.call_llm", return_value=return_str)


# ===========================================================================
# Test 1: Clear solar reduction
# ===========================================================================
def test_clear_solar_reduction():
    expected_llm_out = {"type": "solar_reduction", "hours": [12, 13], "factor": 0.25}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(1, "Panel cleaning from noon to 2 PM leaves 25% output.")
        
    assert result["type"] == "solar_reduction"
    assert result["hours"] == [12, 13]
    assert result["factor"] == 0.25
    assert result["source_note_id"] == 1


# ===========================================================================
# Test 2: Battery reserve instruction
# ===========================================================================
def test_battery_reserve_instruction():
    expected_llm_out = {"type": "minimum_battery_reserve", "hours": [20, 21], "minimum_energy_kwh": 100}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(2, "Keep at least 100 kWh in the battery between 8 PM and 10 PM.")
        
    assert result["type"] == "minimum_battery_reserve"
    assert result["hours"] == [20, 21]
    assert result["minimum_energy_kwh"] == 100


# ===========================================================================
# Test 3: No charging instruction
# ===========================================================================
def test_no_charging_instruction():
    expected_llm_out = {"type": "no_charge_window", "hours": [18, 19]}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(3, "Do not charge the battery between 6 PM and 8 PM.")
        
    assert result["type"] == "no_charge_window"
    assert result["hours"] == [18, 19]


# ===========================================================================
# Test 4: Irrelevant note
# ===========================================================================
def test_irrelevant_note():
    expected_llm_out = {"type": "no_op"}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(4, "The manager meeting is at 3 PM.")
        
    assert result["type"] == "no_op"


# ===========================================================================
# Test 5: Ambiguous instruction
# ===========================================================================
def test_ambiguous_instruction():
    expected_llm_out = {"type": "no_op"}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(5, "Solar might be affected tomorrow.")
        
    assert result["type"] == "no_op"


# ===========================================================================
# Test 6: Paraphrase handling
# ===========================================================================
@pytest.mark.parametrize("phrase", [
    "one fifth output",
    "20 percent generation",
    "80 percent reduction"
])
def test_paraphrase_handling(phrase):
    # Regardless of the paraphrase, the system prompt forces the LLM to normalize
    # it to the same strict schema. We mock that normalized output here.
    expected_llm_out = {"type": "solar_reduction", "hours": [12], "factor": 0.2}
    
    with mock_call_llm(expected_llm_out):
        result = parse_operator_note(6, f"At noon, expect {phrase}.")
        
    assert result["type"] == "solar_reduction"
    assert result["factor"] == 0.2


# ===========================================================================
# Test 7: Invalid LLM output (safe failure)
# ===========================================================================
def test_invalid_llm_output():
    # 1. Invalid JSON string
    with mock_call_llm("This is not JSON!"):
        result = parse_operator_note(7, "Some note")
    assert result["type"] == "no_op"
    assert "PARSER FAILED" in result["raw_text"]
    
    # 2. Valid JSON, but violates schema (unsupported type)
    with mock_call_llm({"type": "invented_action"}):
        result = parse_operator_note(8, "Some note")
    assert result["type"] == "no_op"

    # 3. Valid JSON, but violates schema (wrong type for factor)
    with mock_call_llm({"type": "solar_reduction", "hours": [12], "factor": "a lot"}):
        result = parse_operator_note(9, "Some note")
    assert result["type"] == "no_op"


# ===========================================================================
# Test 8: End-to-end integration
# ===========================================================================
def test_end_to_end_integration():
    """
    Simulates the entire pipeline: 
    Note -> LLM Parser (mocked) -> Compiler -> Optimizer
    """
    # 1. Raw note
    note = "Cut solar to 50% from 1 PM to 3 PM."
    
    # 2. LLM Parser
    expected_llm_out = {"type": "solar_reduction", "hours": [13, 14], "factor": 0.5}
    with mock_call_llm(expected_llm_out):
        raw_dict = parse_operator_note(10, note)
        
    assert raw_dict["type"] == "solar_reduction"
    
    # 3. Directive Compiler
    battery_capacity = 200.0
    constraints = parse_and_compile([raw_dict], battery_capacity=battery_capacity)
    
    assert len(constraints) == 1
    assert constraints[0].source_note_id == 10
    
    # 4. Optimizer
    hours = [
        HourData(hour=h, demand_kwh=100, solar_kwh=50, tariff_bdt_per_kwh=10)
        for h in range(24)
    ]
    battery = BatteryConfig(
        capacity_kwh=battery_capacity,
        initial_energy_kwh=100,
        minimum_energy_kwh=20,
        max_charge_kwh_per_hour=50,
        max_discharge_kwh_per_hour=50,
    )
    scenario = EnergyScenario(hours=hours, battery=battery)
    
    result = optimize_energy(scenario, directives=constraints)
    
    # Verify optimizer succeeded
    assert result.success is True
