"""
GridWise LLM Interpretation Layer (Phase 3)

Public API for parsing human operator notes into strict structured
JSON dictionaries that the Phase 2 Directive Compiler can consume.

Usage:
    from llm import parse_operator_note
    
    note = "Panel cleaning from noon to 2 PM leaves 25% output."
    raw_dict = parse_operator_note(note_id=1, text=note)
    
    # Pass to Phase 2
    from directives import parse_and_compile
    constraints = parse_and_compile([raw_dict], battery_capacity=200)
"""

from .parser import parse_operator_note

__all__ = ["parse_operator_note"]
