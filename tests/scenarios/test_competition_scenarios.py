"""
GridWise API — Competition Scenario Tests

Simulates realistic, end-to-end competition scenarios via the FastAPI app.
"""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from config import Settings

client = TestClient(app, raise_server_exceptions=False)


def build_scenario_payload(scenario_id: str, notes: list[str] = None) -> dict:
    """Helper to build a realistic 24-hour competition payload."""
    # A generic curve: low demand at night, solar in day, peak demand in evening.
    hours = []
    for h in range(24):
        if 8 <= h <= 16:
            solar = 50.0  # Daylight
        else:
            solar = 0.0
            
        if 18 <= h <= 22:
            demand = 120.0 # Evening peak
            tariff = 15.0  # Peak tariff
        else:
            demand = 30.0  # Off-peak
            tariff = 5.0   # Off-peak tariff
            
        hours.append({
            "hour": h,
            "demand_kwh": demand,
            "solar_kwh": solar,
            "tariff_bdt_per_kwh": tariff
        })
        
    payload = {
        "scenario_id": scenario_id,
        "hours": hours,
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 50,
            "minimum_energy_kwh": 10,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        }
    }
    if notes:
        payload["operator_notes"] = notes
    return payload


# ===========================================================================
# Scenario 1: Normal Operation
# ===========================================================================
def test_scenario_1_normal_operation():
    """Test 1: Optimization succeeds without operator notes."""
    payload = build_scenario_payload("COMP-SCENARIO-1")
    
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["scenario_id"] == "COMP-SCENARIO-1"
    assert data["validation"]["success"] is True
    assert data["solver_status"] == "OPTIMAL"
    assert len(data["hourly_plan"]) == 24


# ===========================================================================
# Scenario 2: Multiple Operator Notes
# ===========================================================================
def test_scenario_2_multiple_operator_notes():
    """Test 2: Multiple independent directives processed successfully."""
    notes = [
        "Solar is reduced by 50% between 10:00 and 12:00 due to maintenance.",
        "Do not discharge the battery at 19:00"
    ]
    payload = build_scenario_payload("COMP-SCENARIO-2", notes)
    
    # Mock LLM JSON output for the notes
    outputs = [
        json.dumps({"type": "solar_reduction", "hours": [10, 11, 12], "factor": 0.5}),
        json.dumps({"type": "no_discharge_window", "hours": [19]}),
    ]
    
    with patch("llm.parser.call_llm", side_effect=outputs):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["success"] is True
    
    interp = data["directive_interpretation"]
    assert len(interp) == 2
    assert interp[0]["directive_type"] == "solar_reduction"
    assert interp[1]["directive_type"] == "no_discharge_window"
    
    # Verify the optimizer actually respected the no-discharge window
    plan_hour_19 = next(h for h in data["hourly_plan"] if h["hour"] == 19)
    assert plan_hour_19["battery_kwh"] >= 0.0


# ===========================================================================
# Scenario 3: Irrelevant Notes
# ===========================================================================
def test_scenario_3_irrelevant_notes():
    """Test 3: Non-operational notes are mapped to no_op."""
    notes = ["Team meeting at 3 PM in the main conference room."]
    payload = build_scenario_payload("COMP-SCENARIO-3", notes)
    
    with patch("llm.parser.call_llm", return_value=json.dumps({"type": "no_op"})):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["success"] is True
    assert data["directive_interpretation"][0]["directive_type"] == "no_op"


# ===========================================================================
# Scenario 4: LLM Failure Simulation
# ===========================================================================
def test_scenario_4_llm_failure_simulation():
    """Test 4: If the LLM throws an error (e.g. timeout), it safely falls back."""
    notes = ["Battery reserve 50kWh at 5 AM"]
    payload = build_scenario_payload("COMP-SCENARIO-4", notes)
    
    with patch("llm.parser.call_llm", side_effect=Exception("Connection timed out")):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    
    # Optimizer still runs successfully without the constraint
    assert data["validation"]["success"] is True
    
    # The parsing should show an error status
    interp = data["directive_interpretation"][0]
    assert interp["applies"] is False
    assert interp["directive_type"] == "no_op"


# ===========================================================================
# Scenario 5: Impossible Optimization
# ===========================================================================
def test_scenario_5_impossible_optimization():
    """Test 5: An overly constrained situation results in graceful failure."""
    # We will force a situation where the grid is capped at 0, battery is empty, and demand is high
    payload = build_scenario_payload("COMP-SCENARIO-5")
    payload["battery"]["initial_energy_kwh"] = 0
    payload["battery"]["minimum_energy_kwh"] = 0
    payload["battery"]["max_discharge_kwh_per_hour"] = 0.001 # Practically no battery help
    
    notes = ["Zero grid import allowed at 20:00"]
    payload["operator_notes"] = notes
    
    # At 20:00, demand is 120 and solar is 0. If grid is capped at 0 and battery cannot discharge,
    # it is physically impossible to meet the 120 kWh demand.
    outputs = [json.dumps({"type": "max_grid_window", "hours": [20], "max_grid_kwh": 0.0})]
    
    with patch("llm.parser.call_llm", side_effect=outputs):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    
    # The API returns 200, but validation.success is False
    assert data["validation"]["success"] is False
    assert data["solver_status"] == "FAILED"
    assert "infeasible" in data["validation"]["errors"][0].lower()
