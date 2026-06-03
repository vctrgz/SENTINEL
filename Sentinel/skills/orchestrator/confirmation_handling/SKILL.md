# Skill: confirmation_handling

## Description
Manage user confirmation for critical operations.

---

## Capabilities
- Present actions requiring approval
- Request explicit confirmation
- Interpret user responses

---

## How to Think
- Safety over speed
- Require explicit approval
- Ensure user understands the action

---

## Rules
- ALWAYS require clear yes/no confirmation
- DO NOT proceed without approval
- DO NOT assume intent

---

## When to Use
- During Human-In-The-Loop flow
- When supervisor flags critical commands

---

## When NOT to Use
- For safe operations
- When no user interaction is needed

---

## Output Expectations
- Clear confirmation request

---

## Output Format
Plain text

---

## Failure Modes
- Ambiguous confirmation → must retry
- Silent execution → forbidden

---

## Examples

### Input
["<native package manager> install nginx"]

### Output
"Se va a instalar nginx en el sistema. ¿Deseas continuar? (y/n)"
