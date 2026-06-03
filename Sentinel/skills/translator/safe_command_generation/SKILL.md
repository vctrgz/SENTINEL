# Skill: safe_command_generation

## Description
Ensure generated commands are safe and non-destructive by default.

---

## Capabilities
- Detect potentially dangerous operations
- Prefer safe alternatives
- Reduce risk when possible

---

## How to Think
- Safety first, execution second
- Assume the environment is sensitive
- Avoid irreversible actions

---

## Rules
- DO NOT generate destructive commands unless explicitly required
- Prefer read-only operations
- Avoid system-wide changes

---

## When to Use
- When generating any command
- When uncertainty about impact exists

---

## When NOT to Use
- When explicitly instructed to perform destructive actions

---

## Output Expectations
- Commands with minimized risk

---

## Output Format
Same as command_generation

---

## Failure Modes
- Generating unsafe commands unnecessarily
- Blocking valid operations incorrectly

---

## Examples

### Input
"eliminar archivo test.txt"

### Output
{
  "commands": [
    {"cmd": "rm test.txt", "risk": "medium"}
  ]
}