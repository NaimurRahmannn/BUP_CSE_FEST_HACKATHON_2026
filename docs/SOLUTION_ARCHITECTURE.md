# GridWise LLM Solution Architecture

## Overview

This document defines the technical architecture for the GridWise LLM
system.

The system follows a hybrid architecture:

Natural Language Understanding + Deterministic Constraint Compilation +
Mathematical Optimization + Independent Verification

The LLM is not responsible for making energy decisions.

------------------------------------------------------------------------

# High Level Architecture

Operator Notes \| v LLM Interpretation Layer \| v Directive JSON \| v
Directive Compiler \| v Constraint Validation Layer \| v Optimization
Engine \| v Schedule Verification \| v API Response

------------------------------------------------------------------------

# Components

## 1. API Layer

Technology: FastAPI

Responsibilities: - Receive optimization requests - Validate input
schema - Trigger processing pipeline - Return final JSON response

------------------------------------------------------------------------

## 2. LLM Interpretation Layer

Responsibilities:

Input: Human operator notes

Output: Structured directive objects

The output must contain:

-   directive type
-   affected hours
-   numerical parameters
-   confidence/validation metadata if needed

The LLM must never: - create schedules - modify energy values - make
optimization decisions

------------------------------------------------------------------------

## 3. Directive Compiler

Purpose:

Convert semantic meaning into mathematical constraints.

Examples:

Natural language:

"Do not charge battery from 18 to 20"

Compiler output:

charge\[18\] = 0 charge\[19\] = 0 charge\[20\] = 0

Natural language:

"Solar output is 30% from noon to 2 PM"

Compiler output:

available_solar\[h\] = original_solar\[h\] \* 0.3

------------------------------------------------------------------------

# 4. Optimization Engine

The optimization engine solves:

Minimize:

sum(grid_energy\[h\] \* electricity_price\[h\])

Variables:

grid\[h\] solar_used\[h\] charge\[h\] discharge\[h\] battery_energy\[h\]

Constraints:

Energy balance:

grid + solar + discharge = demand + charge

Battery transition:

battery_next = battery_current + charge - discharge

Limits:

battery_min \<= battery_energy \<= battery_capacity

charge \<= maximum_charge

discharge \<= maximum_discharge

------------------------------------------------------------------------

# 5. Verification Layer

Every generated schedule must be checked.

Verification includes:

-   Energy balance
-   Battery limits
-   Final battery state
-   Directive compliance
-   Output schema validity

Invalid solutions must never be returned.

------------------------------------------------------------------------

# Design Principle

The system should behave like a safety-critical energy management
system.

LLM interprets. Compiler formalizes. Optimizer decides. Verifier
approves.
