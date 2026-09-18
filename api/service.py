"""
GridWise API — Service Layer

Orchestrates the entire GridWise pipeline:
1. HTTP Schema -> Engine Schema mapping
2. LLM Interpretation
3. Directive Compilation 
4. Energy Optimization 
5. Validation 
6. Engine Schema -> HTTP Schema mapping
"""

import logging
import time

from api.schemas import (
    DirectiveInterpretationResponse,
    HourlyPlanResponse,
    OptimizeRequest,
    OptimizeResponse,
    SummaryResponse,
    ValidationResponse,
)
from config import settings
from directives import parse_and_compile
from llm import parse_operator_notes
from optimizer import optimize_energy
from optimizer.models import BatteryConfig, EnergyScenario, HourData
from optimizer.validator import validate_and_update

logger = logging.getLogger(__name__)


def run_optimization(request: OptimizeRequest) -> OptimizeResponse:
    """Executes the complete optimization pipeline for an incoming request."""
    
    # 1. Map to Engine Scenario
    battery = BatteryConfig(
        capacity_kwh=request.battery.capacity_kwh,
        initial_energy_kwh=request.battery.initial_energy_kwh,
        minimum_energy_kwh=request.battery.minimum_energy_kwh,
        max_charge_kwh_per_hour=request.battery.max_charge_kwh_per_hour,
        max_discharge_kwh_per_hour=request.battery.max_discharge_kwh_per_hour,
    )
    
    hours = [
        HourData(
            hour=h.hour,
            demand_kwh=h.demand_kwh,
            solar_kwh=h.solar_kwh,
            tariff_bdt_per_kwh=h.tariff_bdt_per_kwh,
        )
        for h in request.hours
    ]
    
    scenario = EnergyScenario(hours=hours, battery=battery)
    
    # 2. LLM Parsing
    raw_notes = []
    if request.operator_notes:
        raw_notes = [{"id": i, "text": text} for i, text in enumerate(request.operator_notes)]
        
    parsed_json_directives = parse_operator_notes(raw_notes)
    
    # Track the interpretation for the HTTP response
    interpretations = []
    for d in parsed_json_directives:
        dir_type = d.get("type", "unknown")
        interpretations.append(
            DirectiveInterpretationResponse(
                note_index=d.get("source_note_id", -1),
                applies=(d.get("parse_status", "unknown") == "success" and dir_type != "no_op"),
                directive_type=dir_type,
                structured_adjustment={k: v for k, v in d.items() if k not in ("source_note_id", "raw_text", "parse_status", "type", "confidence")},
                explanation=f"Processed note '{d.get('raw_text', '')}' as {dir_type}" if dir_type != "no_op" else "Note was not actionable.",
            )
        )
        
    # 3. Directive Compilation
    try:
        constraints = parse_and_compile(parsed_json_directives, battery_capacity=battery.capacity_kwh)
    except Exception as e:
        logger.exception("Directive compilation failed:")
        return OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            validation=ValidationResponse(success=False, errors=[f"Compilation Error: {e}"]),
            pipeline_version=settings.pipeline_version,
        )
        
    # 4. Optimization
    t0 = time.time()
    try:
        result = optimize_energy(scenario, constraints)
    except Exception as e:
        logger.exception("Optimization engine crashed:")
        return OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            validation=ValidationResponse(success=False, errors=[f"Optimizer Error: {e}"]),
            pipeline_version=settings.pipeline_version,
        )
    opt_time_ms = (time.time() - t0) * 1000.0
        
    # 5. Independent Validation
    if not result.success:
        return OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            validation=ValidationResponse(success=False, errors=["Optimizer reported infeasible model."]),
            solver_status="FAILED",
            optimization_time_ms=opt_time_ms,
            pipeline_version=settings.pipeline_version,
        )
        
    # Validates in-place and sets result.validation_passed / result.validation_errors
    result = validate_and_update(result, scenario, constraints)
    
    # 6. Map to HTTP Response
    hourly_plan = [
        HourlyPlanResponse(
            hour=hp.hour,
            grid_kwh=hp.grid_kwh,
            battery_energy_after_kwh=hp.battery_energy_after_kwh,
            battery_kwh=hp.battery_kwh if hp.battery_action.value == "charge" else -hp.battery_kwh if hp.battery_action.value == "discharge" else 0.0,
        )
        for hp in result.hourly_plan
    ]
    
    summary = SummaryResponse(
        total_grid_kwh=result.total_grid_kwh,
        total_cost_bdt=result.total_cost_bdt,
        peak_grid_kwh=result.peak_grid_kwh,
        plan_summary=f"Optimized schedule. Cost: {result.total_cost_bdt} BDT.",
    )
    
    validation = ValidationResponse(
        success=result.validation_passed,
        errors=result.validation_errors,
    )
    
    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=interpretations,
        hourly_plan=hourly_plan,
        summary=summary,
        validation=validation,
        solver_status="OPTIMAL",
        optimization_time_ms=opt_time_ms,
        pipeline_version=settings.pipeline_version,
    )
