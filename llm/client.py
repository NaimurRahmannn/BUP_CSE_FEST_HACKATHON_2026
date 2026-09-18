"""
GridWise LLM Interpretation Layer — API Client

Handles communication with the Google GenAI provider.
Loads credentials from .env.
"""

import os
from typing import Any

from google import genai
from google.genai import types

from .prompts import SYSTEM_PROMPT
from .schemas import LLMDirectiveOutput
from config import settings

# Initialize the GenAI client using central settings
_client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options={"timeout": settings.llm_timeout_seconds}
)
_model_name = settings.gemini_model


def call_llm(operator_note: str) -> dict[str, Any]:
    """Call the LLM with the operator note and return the parsed JSON dictionary.
    
    Args:
        operator_note: The raw text from the operator.
        
    Returns:
        A dictionary matching the LLMDirectiveOutput schema.
        
    Raises:
        Exception: If the API call fails or times out.
    """
    # Configure the generation request to force JSON output matching the Pydantic schema
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=LLMDirectiveOutput,
        temperature=0.0, # Deterministic interpretation
    )

    response = _client.models.generate_content(
        model=_model_name,
        contents=operator_note,
        config=config,
    )
    
    # We parse the text output into a python dict via pydantic for validation
    # Actually, google-genai structured output guarantees it returns JSON that conforms.
    # We will pass the raw JSON string to parser.py which will validate it.
    
    # The response.text is guaranteed to be a JSON string.
    return response.text
