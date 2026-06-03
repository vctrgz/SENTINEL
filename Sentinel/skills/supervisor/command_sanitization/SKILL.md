# Skill: command_sanitization

## Description
Clean and normalize commands to ensure safe and consistent execution.

---

## Capabilities
- Remove unnecessary or dangerous flags
- Normalize syntax
- Enforce safe defaults

---

## How to Think
- Simplicity over complexity
- Remove anything not strictly needed
- Avoid risky flags unless required

---

## Rules
- DO NOT alter command intent
- REMOVE unnecessary sudo usage
- ENSURE command is minimal

---

## When to Use
- After command generation
- Before risk analysis

---

## When NOT to Use
- When command is already validated

---

## Output Expectations
- Cleaned commands

---

## Output Format
{
  "commands": [
    {"cmd": "string"}
  ]
}

---

## Failure Modes
- Over-modifying commands
- Breaking valid commands

---

## Examples

### Input
"sudo ls -la"

### Output
{
  "commands": [
    {"cmd": "ls -la"}
  ]
}