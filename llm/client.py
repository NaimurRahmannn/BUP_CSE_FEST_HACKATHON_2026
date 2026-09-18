"""
GridWise LLM Interpretation Layer — API Client

Handles communication with the Google GenAI provider.
Loads credentials from .env.
"""

import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .prompts import SYSTEM_PROMPT
from .schemas import LLMDirectiveOutput

# Load environment variables
load_dotenv()

# Initialize the GenAI client
_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
_client = genai.Client(api_key=_api_key)
_model_name = os.getenv("GOOGLE_GEMINI_MODEL", "gemini-3-flash")


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
