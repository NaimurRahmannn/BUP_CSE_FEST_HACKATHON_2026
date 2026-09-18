"""
GridWise LLM Interpretation Layer — Parser

Validates the LLM output and handles graceful fallbacks.
Converts the raw textual LLM output into a validated JSON dict
ready for the Phase 2 compiler.
"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from .client import call_llm
from .schemas import LLMDirectiveOutput

logger = logging.getLogger(__name__)


def parse_operator_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse multiple operator notes independently.
    
    Args:
        notes: List of dicts, each containing 'id' and 'text'.
        
    Returns:
        List of parsed directive dictionaries, preserving source metadata.
    """
    directives = []
    for note in notes:
        d = parse_operator_note(note["id"], note["text"])
        directives.append(d)
    return directives


def parse_operator_note(note_id: int, text: str) -> dict[str, Any]:
    """Parse a human operator note into a strict JSON directive dictionary.
    
    Args:
        note_id: The ID of the operator note (for Phase 2 traceability).
        text: The raw text to parse.
        
    Returns:
        A dictionary perfectly conforming to the Phase 2 DirectiveCompiler
        expected input schema. Safe fallbacks to `no_op` are provided on failure.
    """
    try:
        # 1. Call the LLM provider
        raw_json_str = call_llm(text)
        
        # 2. Parse the string into a python dictionary
        try:
            parsed_dict = json.loads(raw_json_str)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e} | Raw: {raw_json_str}")
            return _safe_fallback(note_id, text, "validation_failed", str(e))
            
        # 3. Validate against strict schema
        try:
            validated_model = LLMDirectiveOutput.model_validate(parsed_dict)
        except ValidationError as e:
            logger.error(f"LLM returned JSON violating schema: {e} | JSON: {parsed_dict}")
            return _safe_fallback(note_id, text, "validation_failed", str(e))
            
        # 4. Transform back to dictionary matching Phase 2 discriminated union
        final_dict = validated_model.to_phase2_dict()
        
        # 5. Inject traceability metadata
        final_dict["source_note_id"] = note_id
        final_dict["raw_text"] = text
        # Currently no confidence metric exposed natively via google-genai structured output,
        # but we could set it to 1.0 or None. Phase 2 handles None.
        final_dict["confidence"] = None 
        final_dict["parse_status"] = "success"
        
        return final_dict

    except Exception as e:
        # Catch network timeouts, API errors, etc.
        logger.error(f"LLM API call failed: {e}")
        return _safe_fallback(note_id, text, "llm_error", str(e))


def _safe_fallback(note_id: int, text: str, status: str = "fallback", error_msg: str = "") -> dict[str, Any]:
    """Return a safe no_op directive upon catastrophic failure."""
    fallback_dict = {
        "type": "no_op",
        "source_note_id": note_id,
        "raw_text": text,
        "confidence": 0.0,
        "parse_status": status,
    }
    if error_msg:
        fallback_dict["error_message"] = error_msg
    return fallback_dict
