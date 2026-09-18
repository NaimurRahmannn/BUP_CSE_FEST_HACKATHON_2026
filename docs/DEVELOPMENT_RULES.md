# Development Rules

## General Rules

This project is competition software.

Prioritize:

1.  Correctness
2.  Reliability
3.  Testability
4.  Simplicity

------------------------------------------------------------------------

# Before Coding

The coding agent must:

1.  Read all files in /doc.
2.  Understand the current phase.
3.  Inspect existing implementation.
4.  Avoid unnecessary redesign.

------------------------------------------------------------------------

# Architecture Rules

Do not:

-   Move optimization logic into the LLM.
-   Remove validation layers.
-   Replace mathematical optimization with heuristics.
-   Hardcode sample scenarios.
-   Add unnecessary dependencies.

------------------------------------------------------------------------

# Code Quality Rules

Prefer:

-   Small modules
-   Clear interfaces
-   Unit tests
-   Type validation
-   Deterministic behavior

------------------------------------------------------------------------

# Changes

Before major changes explain:

-   Why the change is needed.
-   What problem it solves.
-   Possible risks.

------------------------------------------------------------------------

# Testing

Every important module must have tests.

Critical tests:

-   Battery behavior
-   Energy balance
-   Directive enforcement
-   Invalid inputs
-   Edge cases
