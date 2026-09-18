# GridWise API Usage Guide

The GridWise LLM pipeline is accessed via a FastAPI REST interface. All endpoints consume and produce strict JSON.

## Endpoints

### 1. Health Check
`GET /health`
Returns a basic 200 OK to verify the API server is reachable.
```json
{
  "status": "ok"
}
```

---

### 2. Optimize Energy
`POST /optimize-energy`
The primary endpoint for executing the full pipeline.

#### Request Format
```json
{
  "scenario_id": "TEST-01",
  "battery": {
    "capacity_kwh": 200,
    "initial_energy_kwh": 100,
    "minimum_energy_kwh": 20,
    "max_charge_kwh_per_hour": 50,
    "max_discharge_kwh_per_hour": 50
  },
  "hours": [
    {
      "hour": 0,
      "demand_kwh": 100,
      "solar_kwh": 0,
      "tariff_bdt_per_kwh": 10
    }
    // ... exactly 24 hour objects total (0-23)
  ],
  "operator_notes": [
    {
      "id": 1,
      "text": "Grid is constrained to 20 kWh at 7 PM"
    }
  ]
}
```

#### Successful Response (200 OK)
```json
{
  "scenario_id": "TEST-01",
  "directive_interpretation": [
    {
      "original_note_id": 1,
      "raw_text": "Grid is constrained to 20 kWh at 7 PM",
      "parsed_directive": {
        "type": "max_grid_window",
        "hours": [19],
        "max_grid_kwh": 20.0
      },
      "parse_status": "success"
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_import_kwh": 100.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_energy_kwh": 100.0
    }
    // ... 24 hours of plan ...
  ],
  "summary": {
    "total_grid_kwh": 1500.0,
    "total_cost_bdt": 18000.0,
    "peak_grid_kwh": 100.0
  },
  "validation": {
    "success": true,
    "errors": []
  },
  "solver_status": "OPTIMAL",
  "optimization_time_ms": 125.4,
  "pipeline_version": "1.0"
}
```

#### Error Responses

**422 Unprocessable Entity**
Returned when the JSON payload fails Pydantic validation (e.g., missing hours, negative battery capacities, missing fields).
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "hours"],
      "msg": "Value error, Exactly 24 hours required, got 23",
      "input": [...]
    }
  ],
  "body": {...}
}
```

**500 Internal Server Error**
Returned during catastrophic system failures. The actual stack trace is suppressed from the response to prevent data leakage but is printed cleanly in the backend logs using `logger.exception()`.
```json
{
  "detail": "Internal Server Error"
}
```
