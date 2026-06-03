# Skill: objective_structuring

## Description
Transform an interpreted objective into a structured JSON format.

---

## Capabilities
- Convert objectives into structured representations
- Add metadata such as priority and constraints
- Normalize outputs for downstream agents

---

## How to Think
- Structure is more important than verbosity
- Keep the format minimal but complete
- Avoid unnecessary fields

---

## Rules
- ALWAYS follow the required JSON schema
- DO NOT include explanations
- DO NOT modify the original intent

---

## When to Use
- After interpreting user intent
- Before sending data to Planner

---

## When NOT to Use
- When working with already structured JSON
- When interacting with the user

---

## Output Expectations
- Clean structured JSON

---

## Output Format
{
  "objective": "string",
  "constraints": [],
  "priority": "low|medium|high"
}

---

## Failure Modes
- Missing fields → must be filled with defaults
- Ambiguous priority → default to "medium"

---

## Examples

### Input
"listar los archivos del directorio actual"

### Output
{
  "objective": "listar los archivos del directorio actual",
  "constraints": [],
  "priority": "low"
}