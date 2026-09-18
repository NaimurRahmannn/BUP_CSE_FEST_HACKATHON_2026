# GridWise LLM Project Context

## Project Purpose

This project is a solution for the BUP CSE FEST 2026 GridWise LLM
Challenge.

The system receives: - Campus energy scenario data - Battery
specifications - Human-written operator notes in natural language

The system must:

1.  Understand operator instructions.
2.  Convert those instructions into structured energy directives.
3.  Apply those directives as mathematical constraints.
4.  Optimize the 24-hour energy schedule.
5.  Return a valid, verified JSON response.

------------------------------------------------------------------------

# Core Architecture Principle

The LLM is NOT an optimizer.

The LLM is only responsible for semantic understanding and converting
human language into structured directives.

Energy decisions must be made by deterministic optimization algorithms.

The intended pipeline is:

Operator Notes \| v LLM Interpretation Layer \| v Structured Directive
JSON \| v Directive Validation Layer \| v Optimization Engine \| v
Solution Verification Layer \| v Final API Response

------------------------------------------------------------------------

# Non-Negotiable Engineering Rules

1.  Never allow the LLM to directly generate the final energy schedule.

2.  Never trust raw LLM output without validation.

3.  All directives must be converted into deterministic constraints.

4.  The optimizer must satisfy every hard constraint.

5.  The final solution must be independently verified before returning.

6.  Do not replace mathematical optimization with heuristic guesses.

7.  Do not remove safety checks for simplicity.

------------------------------------------------------------------------

# Supported Directive Types

Only the following directive categories are allowed:

-   solar_reduction
-   minimum_battery_reserve
-   no_charge_window
-   no_discharge_window
-   max_grid_window
-   no_op

Unknown or unsupported instructions should not create invented behavior.

------------------------------------------------------------------------

# Optimization Objective

The objective is to minimize electricity cost:

Total Cost = Sum(grid_energy\[h\] \* electricity_tariff\[h\])

Subject to:

-   Hourly energy balance
-   Solar availability limits
-   Battery capacity constraints
-   Battery charge/discharge limits
-   Minimum reserve requirements
-   Operator directive constraints
-   Final battery state requirements

------------------------------------------------------------------------

# Energy Model Understanding

For every hour:

Grid + Solar Used + Battery Discharge = Energy Demand + Battery Charge

Battery state transition:

Battery Energy(next hour) = Battery Energy(current hour) + Charging -
Discharging

The optimizer must never violate battery limits.

------------------------------------------------------------------------

# System Components

## 1. API Service

Responsibilities: - Receive optimization requests - Validate input
format - Return final JSON response

## 2. LLM Interpreter

Responsibilities: - Understand operator language - Identify directive
type - Extract hours and numerical values - Return structured JSON only

The LLM must not optimize.

## 3. Directive Compiler

Responsibilities: - Convert structured directives into mathematical
constraints.

Example:

"No charging from 18 to 20"

becomes:

battery_charge\[18\] = 0 battery_charge\[19\] = 0 battery_charge\[20\] =
0

## 4. Optimization Engine

Responsibilities: - Solve energy scheduling problem - Minimize cost -
Respect all constraints

## 5. Verification Engine

Responsibilities: - Replay the generated schedule - Check energy
balance - Check battery validity - Check every directive - Reject
invalid schedules

------------------------------------------------------------------------

# Development Strategy

Build incrementally:

## Phase 1

Build and verify optimization engine.

No LLM integration.

Focus: - Mathematical correctness - Battery modeling - Cost minimization

## Phase 2

Build directive compiler and constraint system.

Focus: - Correct transformation from directives to constraints.

## Phase 3

Integrate LLM interpretation.

Focus: - Robust natural language understanding. - Strict JSON output.

## Phase 4

Build complete API system.

Focus: - Request handling - Response formatting - Reliability

## Phase 5

Adversarial testing and competition preparation.

Focus: - Edge cases - Paraphrases - Invalid inputs - Conflicting
instructions

------------------------------------------------------------------------

# Coding Agent Instructions

Before writing code:

1.  Read this document.
2.  Read the complete problem statement documents.
3.  Understand the current development phase.
4.  Inspect existing code before making changes.

When requirements are unclear:

-   Explain assumptions.
-   Avoid guessing.
-   Prefer asking for clarification.

Before changing architecture:

Explain: - Why the change is required. - What problem it solves. -
Possible risks.

------------------------------------------------------------------------

# Preferred Engineering Style

Prefer:

-   Simple architecture
-   Modular code
-   Clear interfaces
-   Strong validation
-   Automated tests
-   Reproducible behavior

Avoid:

-   Unnecessary frameworks
-   Hardcoded competition scenarios
-   Hidden assumptions
-   Duplicate logic
-   Overcomplicated abstractions

------------------------------------------------------------------------

# Project Philosophy

The winning approach is:

LLM = Translator

Compiler = Constraint Builder

Optimizer = Decision Maker

Validator = Safety System

The system should behave like a careful human energy operator: -
Understand instructions. - Convert them into rules. - Optimize
intelligently. - Verify before execution.
