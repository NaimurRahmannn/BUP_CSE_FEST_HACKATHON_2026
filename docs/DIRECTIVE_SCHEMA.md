# GridWise LLM Directive Schema

This document defines the strict contract between the Phase 3 LLM output and the Phase 2 Directive Compiler. It specifies the expected structured JSON format for all supported operator directives.

## 1. solar_reduction

**Purpose:**  
Reduce available solar generation during specific hours, typically for maintenance or weather predictions.

**Valid JSON:**
```json
{
  "type": "solar_reduction",
  "hours": [12, 13],
  "factor": 0.5
}
```

**Required Fields:**
- `type` (string): Must be `"solar_reduction"`
- `hours` (list of int): Affected hours
- `factor` (float): The multiplier to apply to original solar generation

**Validation Rules:**
- `hours`: 0–23, unique, sorted ascending
- `factor`: `0 < factor <= 1`

**Meaning:**  
`effective_solar[h] = original_solar[h] * factor`

**Example Invalid Input:**
```json
{
  "type": "solar_reduction",
  "hours": [25],
  "factor": 1.5
}
```
*(Raises `InvalidHourError` for 25, and `InvalidParameterError` for 1.5)*

---

## 2. minimum_battery_reserve

**Purpose:**  
Ensure the battery energy does not fall below a specified threshold during specific hours.

**Valid JSON:**
```json
{
  "type": "minimum_battery_reserve",
  "hours": [18, 19, 20],
  "minimum_energy_kwh": 200.0
}
```

**Required Fields:**
- `type` (string): Must be `"minimum_battery_reserve"`
- `hours` (list of int): Affected hours
- `minimum_energy_kwh` (float): Minimum energy level in kWh

**Validation Rules:**
- `hours`: 0–23
- `minimum_energy_kwh`: `>= 0`
- Conflict Check: Must not exceed battery capacity.

**Meaning:**  
`battery_energy[h] >= minimum_energy_kwh`

**Example Invalid Input:**
```json
{
  "type": "minimum_battery_reserve",
  "hours": [12],
  "minimum_energy_kwh": -50.0
}
```
*(Raises `InvalidParameterError`)*

---

## 3. no_charge_window

**Purpose:**  
Forbid battery charging during specific hours.

**Valid JSON:**
```json
{
  "type": "no_charge_window",
  "hours": [18, 19, 20]
}
```

**Required Fields:**
- `type` (string): Must be `"no_charge_window"`
- `hours` (list of int): Affected hours

**Validation Rules:**
- `hours`: 0–23

**Meaning:**  
`charge[h] = 0`

**Example Invalid Input:**
```json
{
  "type": "no_charge_window",
  "hours": []
}
```
*(Raises `InvalidParameterError` / Schema Error because `hours` must have at least 1 item)*

---

## 4. no_discharge_window

**Purpose:**  
Forbid battery discharging during specific hours.

**Valid JSON:**
```json
{
  "type": "no_discharge_window",
  "hours": [0, 1, 2]
}
```

**Required Fields:**
- `type` (string): Must be `"no_discharge_window"`
- `hours` (list of int): Affected hours

**Validation Rules:**
- `hours`: 0–23

**Meaning:**  
`discharge[h] = 0`

**Example Invalid Input:**
```json
{
  "type": "no_discharge_window",
  "hours": [-5]
}
```
*(Raises `InvalidHourError`)*

---

## 5. max_grid_window

**Purpose:**  
Limit the maximum amount of grid import during specific hours.

**Valid JSON:**
```json
{
  "type": "max_grid_window",
  "hours": [18],
  "max_grid_kwh": 100.0
}
```

**Required Fields:**
- `type` (string): Must be `"max_grid_window"`
- `hours` (list of int): Affected hours
- `max_grid_kwh` (float): Maximum allowed grid import in kWh

**Validation Rules:**
- `hours`: 0–23
- `max_grid_kwh`: `>= 0`

**Meaning:**  
`grid[h] <= max_grid_kwh`

**Example Invalid Input:**
```json
{
  "type": "max_grid_window",
  "hours": [12],
  "max_grid_kwh": -10.0
}
```
*(Raises `InvalidParameterError`)*

---

## 6. no_op

**Purpose:**  
Indicates an operator note was parsed, but it has no impact on the energy optimization schedule.

**Valid JSON:**
```json
{
  "type": "no_op"
}
```

**Required Fields:**
- `type` (string): Must be `"no_op"`

**Validation Rules:**
- None.

**Meaning:**  
No optimizer modification.

**Example Invalid Input:**
```json
{
  "type": "no_op_action"
}
```
*(Raises `UnsupportedDirectiveError`)*
