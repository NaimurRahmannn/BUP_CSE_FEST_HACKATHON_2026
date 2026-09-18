import os
import time
import json
from api.main import app
from fastapi.testclient import TestClient
from llm.client import call_llm
from directives import parse_and_compile
from optimizer import optimize_energy
from optimizer.models import BatteryConfig, EnergyScenario, HourData

# Initialize
client = TestClient(app, raise_server_exceptions=False)
NOTE = "Do not charge the battery between 18:00 and 20:00"

def get_scenario():
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

def run_benchmarks():
    print("--- GridWise Performance Benchmark ---")
    
    # 1. LLM Processing Time
    print("1. Benchmarking LLM Processing Time...")
    t0 = time.time()
    raw_output = call_llm(NOTE)
    t1 = time.time()
    llm_time = (t1 - t0) * 1000
    print(f"   -> LLM Latency: {llm_time:.2f} ms")
    
    # 2. Directive Compilation Time
    print("2. Benchmarking Directive Compilation Time...")
    parsed_json_directives = [{"source_note_id": 1, "raw_text": NOTE, **json.loads(raw_output)}]
    t0 = time.time()
    constraints = parse_and_compile(parsed_json_directives, battery_capacity=200.0)
    t1 = time.time()
    compile_time = (t1 - t0) * 1000
    print(f"   -> Compiler Latency: {compile_time:.2f} ms")
    
    # 3. Optimization Solver Time
    print("3. Benchmarking Optimization Solver Time...")
    scenario = get_scenario()
    t0 = time.time()
    result = optimize_energy(scenario, constraints)
    t1 = time.time()
    solver_time = (t1 - t0) * 1000
    print(f"   -> Solver Latency: {solver_time:.2f} ms")
    
    # 4. Total API Response Time
    print("4. Benchmarking Total API Response Time (E2E)...")
    payload = {
        "scenario_id": "BENCHMARK-1",
        "hours": [{"hour": h, "demand_kwh": 100, "solar_kwh": 50, "tariff_bdt_per_kwh": 10} for h in range(24)],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 20,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        },
        "operator_notes": [{"id": 1, "text": NOTE}]
    }
    t0 = time.time()
    response = client.post("/optimize-energy", json=payload)
    t1 = time.time()
    api_time = (t1 - t0) * 1000
    print(f"   -> API Latency: {api_time:.2f} ms")
    print("--------------------------------------")
    print(f"E2E API Request Status: {response.status_code}")
    print(f"E2E Reported Optimization Time: {response.json().get('optimization_time_ms', 0):.2f} ms")

if __name__ == "__main__":
    # To run this, the GOOGLE_GEMINI_API_KEY must be valid in .env
    run_benchmarks()
