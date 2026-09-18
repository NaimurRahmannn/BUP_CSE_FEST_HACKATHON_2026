"""
GridWise LLM Interpretation Layer

Public API for parsing human operator notes into strict structured
JSON dictionaries that the Directive Compiler can consume.

Usage:
    from llm import parse_operator_note
    
    note = "Panel cleaning from noon to 2 PM leaves 25% output."
    raw_dict = parse_operator_note(note_id=1, text=note)
    
    # Pass to Compiler
    from directives import parse_and_compile
    constraints = parse_and_compile([raw_dict], battery_capacity=200)
"""

from .parser import parse_operator_note, parse_operator_notes

__all__ = ["parse_operator_note", "parse_operator_notes"]
