# Skill: risk_explanation

## Description
Explain risks associated with system commands or actions.

---

## Capabilities
- Identify potential dangers
- Translate technical risks into understandable language
- Provide consequences of actions

---

## How to Think
- Assume worst-case scenario
- Be explicit and direct
- Do not downplay risks

---

## Rules
- ALWAYS explain consequences
- DO NOT omit critical details
- DO NOT exaggerate unnecessarily

---

## When to Use
- When commands are flagged as risky
- Before requesting user confirmation

---

## When NOT to Use
- When actions are clearly safe
- When no user interaction is required

---

## Output Expectations
- Clear explanation of risk and consequences

---

## Output Format
Plain text

---

## Failure Modes
- Underestimating risk → dangerous
- Overestimating risk → unnecessary friction

---

## Examples

### Input
"rm -rf /"

### Output
"Este comando eliminaría todos los archivos del sistema, lo que podría dejar el sistema inutilizable."