# Skill: ambiguity_resolution

## Description
Detect and handle ambiguous or incomplete user input.

---

## Capabilities
- Identify missing or unclear information
- Detect multiple interpretations
- Generate clarification requests

---

## How to Think
- Never guess when ambiguity is high
- Prefer asking over assuming
- Minimize user friction when clarifying

---

## Rules
- DO NOT fabricate missing details
- Keep clarification questions simple
- Only ask when necessary

---

## When to Use
- When user input is unclear
- When multiple interpretations exist

---

## When NOT to Use
- When the objective is already precise
- When ambiguity does not affect execution

---

## Output Expectations
- Either a refined objective OR a clarification request

---

## Output Format
{
  "status": "clarify|resolved",
  "message": "string"
}

---

## Failure Modes
- Over-asking → avoid unnecessary clarification
- Under-asking → leads to incorrect execution

---

## Examples

### Input
"haz algo con nginx"

### Output
{
  "status": "clarify",
  "message": "¿Qué acción quieres realizar con nginx?"
}