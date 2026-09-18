"""
GridWise API — Integration Tests

Tests the FastAPI endpoints using TestClient.
"""

import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from config import Settings

client = TestClient(app, raise_server_exceptions=False)


def build_valid_request(scenario_id="TEST-01", notes=None):
    """Helper to build a valid optimization request payload."""
    hours = [
        {
            "hour": i,
            "demand_kwh": 100,
            "solar_kwh": 50,
            "tariff_bdt_per_kwh": 10
        }
        for i in range(24)
    ]
    battery = {
        "capacity_kwh": 200,
        "initial_energy_kwh": 100,
        "minimum_energy_kwh": 20,
        "max_charge_kwh_per_hour": 50,
        "max_discharge_kwh_per_hour": 50
    }
    payload = {
        "scenario_id": scenario_id,
        "hours": hours,
        "battery": battery,
    }
    if notes is not None:
        payload["operator_notes"] = notes
    return payload


# ===========================================================================
# Test 1: Health endpoint
# ===========================================================================
def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ===========================================================================
# Test 2: Valid optimization request (No notes)
# ===========================================================================
def test_valid_optimization_request():
    payload = build_valid_request()
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == "TEST-01"
    assert data["validation"]["success"] is True
    assert len(data["hourly_plan"]) == 24
    assert data["summary"]["total_grid_kwh"] >= 0


# ===========================================================================
# Test 3: Multiple operator notes
# ===========================================================================
def test_multiple_notes():
    notes = [
        {"id": 1, "text": "Do not charge at 18:00"},
        {"id": 2, "text": "Clean panels at noon, 50% solar"}
    ]
    payload = build_valid_request("TEST-02", notes)
    
    # Mock the LLM to return valid structured data for both
    outputs = [
        json.dumps({"type": "no_charge_window", "hours": [18]}),
        json.dumps({"type": "solar_reduction", "hours": [12], "factor": 0.5}),
    ]
    
    with patch("llm.parser.call_llm", side_effect=outputs):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["success"] is True
    
    interp = data["directive_interpretation"]
    assert len(interp) == 2
    assert interp[0]["original_note_id"] == 1
    assert interp[0]["parsed_directive"]["type"] == "no_charge_window"
    assert interp[1]["original_note_id"] == 2
    assert interp[1]["parsed_directive"]["type"] == "solar_reduction"


# ===========================================================================
# Test 4: Irrelevant operator note (no_op)
# ===========================================================================
def test_irrelevant_note():
    notes = [{"id": 3, "text": "The manager is visiting today."}]
    payload = build_valid_request("TEST-03", notes)
    
    with patch("llm.parser.call_llm", return_value=json.dumps({"type": "no_op"})):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["success"] is True
    assert data["directive_interpretation"][0]["parsed_directive"]["type"] == "no_op"


# ===========================================================================
# Test 5: Invalid request (422)
# ===========================================================================
def test_invalid_request_422():
    payload = build_valid_request()
    # Remove one hour to invalidate the 24-hour requirement
    payload["hours"].pop()
    
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 422
    assert "Exactly 24 hours required" in str(response.json())


# ===========================================================================
# Test 6: Mock LLM failure (safe fallback)
# ===========================================================================
def test_mock_llm_failure():
    notes = [{"id": 4, "text": "Some text"}]
    payload = build_valid_request("TEST-04", notes)
    
    with patch("llm.parser.call_llm", side_effect=TimeoutError("API Down")):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    # The optimizer should still succeed, just without constraints
    assert data["validation"]["success"] is True
    
    interp = data["directive_interpretation"][0]
    assert interp["parse_status"] == "llm_error"
    assert interp["parsed_directive"]["type"] == "no_op"


# ===========================================================================
# Test 7: Impossible optimization scenario
# ===========================================================================
def test_impossible_optimization():
    payload = build_valid_request("TEST-05")
    # Make demand extremely high, beyond battery + grid bounds (if there were bounds).
    # Since grid is technically unbound, to make it infeasible we can use a directive
    # that conflicts directly with reality.
    
    notes = [{"id": 5, "text": "Max grid is 0 at 18:00"}]
    payload["operator_notes"] = notes
    
    # We also need demand > solar at 18:00, which it is (100 > 50).
    # If battery is empty and max grid is 0, demand cannot be met.
    payload["battery"]["initial_energy_kwh"] = 0
    payload["battery"]["minimum_energy_kwh"] = 0
    # Restrict discharge globally to 0 to prevent battery usage entirely for the whole day
    payload["battery"]["max_discharge_kwh_per_hour"] = 0.001 
    
    outputs = [json.dumps({"type": "max_grid_window", "hours": [18], "max_grid_kwh": 0})]
    
    with patch("llm.parser.call_llm", side_effect=outputs):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["success"] is False
    assert "infeasible" in data["validation"]["errors"][0].lower()


# ===========================================================================
# Test 8: Full end-to-end pipeline trace
# ===========================================================================
def test_full_pipeline_trace():
    """
    Simulates a full pipeline trace:
    Request -> API -> LLM mock -> Compiler -> Optimizer -> Validator -> Response
    """
    notes = [{"id": 99, "text": "Grid is constrained to 20 kWh at 7 PM"}]
    payload = build_valid_request("E2E-TRACE", notes)
    
    # LLM Mock
    outputs = [json.dumps({"type": "max_grid_window", "hours": [19], "max_grid_kwh": 20})]
    
    with patch("llm.parser.call_llm", side_effect=outputs):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 200
    data = response.json()
    
    # Verify interpretation (LLM -> Compiler mapping)
    assert len(data["directive_interpretation"]) == 1
    assert data["directive_interpretation"][0]["parse_status"] == "success"
    
    # Verify optimizer (Optimizer mapping)
    assert data["validation"]["success"] is True
    
    # Verify the grid cap was respected at hour 19 (Validator mapping)
    plan_hour_19 = next(h for h in data["hourly_plan"] if h["hour"] == 19)
    assert plan_hour_19["grid_import_kwh"] <= 20.0
    
    # Verify metadata (Test 5: Response metadata exists)
    assert data["solver_status"] == "OPTIMAL"
    assert data["optimization_time_ms"] >= 0.0
    assert data["pipeline_version"] == "1.0"


# ===========================================================================
# API Hardening Tests
# ===========================================================================

def test_config_loading():
    """Test 1: Environment values load correctly into config."""
    with patch.dict(os.environ, {
        "GOOGLE_GEMINI_API_KEY": "test-key",
        "LLM_TIMEOUT_SECONDS": "15",
        "SOLVER_TIMEOUT_SECONDS": "25",
        "PIPELINE_VERSION": "2.0"
    }):
        s = Settings()
        assert s.gemini_api_key == "test-key"
        assert s.llm_timeout_seconds == 15
        assert s.solver_timeout_seconds == 25
        assert s.pipeline_version == "2.0"


def test_missing_api_key():
    """Test 2: Missing API key triggers clear configuration error."""
    with patch.dict(os.environ, {}, clear=True), patch("config.load_dotenv"):
        s = Settings()
        try:
            s.validate()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "GOOGLE_GEMINI_API_KEY" in str(e)


def test_unexpected_api_exception():
    """Test 4: Unexpected API exception returns safe 500 response."""
    payload = build_valid_request("TEST-ERROR")
    
    # We force a catastrophic crash in the service layer
    with patch("api.main.run_optimization", side_effect=RuntimeError("System core meltdown")):
        response = client.post("/optimize-energy", json=payload)
        
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
