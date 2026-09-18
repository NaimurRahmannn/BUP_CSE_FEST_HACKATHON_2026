# GridWise LLM API Specification

## Health Endpoint

GET /health

Response:

{ "status": "ok" }

------------------------------------------------------------------------

# Optimization Endpoint

POST /optimize-energy

Purpose:

Generate the lowest-cost valid energy schedule.

------------------------------------------------------------------------

# Request Structure

Example:

{ "scenario_id": "example", "operator_notes": \[\], "hours": \[\],
"battery": {} }

------------------------------------------------------------------------

# Processing Flow

1.  Validate request.
2.  Interpret operator notes.
3.  Convert directives into constraints.
4.  Solve optimization problem.
5.  Verify solution.
6.  Return response.

------------------------------------------------------------------------

# Response Requirements

Response should include:

-   scenario_id
-   directive_interpretation
-   hourly_plan
-   total_grid_kwh
-   total_cost_bdt
-   peak_grid_kwh
-   plan_summary

------------------------------------------------------------------------

# Error Handling

The API must gracefully handle:

-   Invalid input
-   Impossible optimization
-   Invalid directives
-   Solver failure

Never return a schedule that violates constraints.
