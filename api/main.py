"""
GridWise API — Main Entrypoint

Defines the FastAPI application and HTTP routes.
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from api.schemas import OptimizeRequest, OptimizeResponse
from api.service import run_optimization

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GridWise LLM Pipeline API",
    description="The core orchestration API connecting the GridWise optimization engine to the competition frontend.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Gracefully handle bad JSON requests with a 422 Unprocessable Entity."""
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "body": jsonable_encoder(exc.body)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch any unhandled exceptions at the API boundary, returning a safe 500."""
    logger.error(f"Unhandled system error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error. Please contact an administrator."},
    )


@app.get("/health")
async def health_check():
    """Simple health check endpoint to verify API availability."""
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy_route(request: OptimizeRequest):
    """
    Executes the full GridWise optimization pipeline:
    1. Parse LLM operator notes (if any)
    2. Compile constraints
    3. Run mathematical optimization engine
    4. Independently validate the schedule
    """
    try:
        response = run_optimization(request)
        return response
    except ValueError as e:
        # Re-raise known value errors as 400 Bad Request
        raise HTTPException(status_code=400, detail=str(e))
