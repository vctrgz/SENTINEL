# Skill: error_aware_translation

## Description
Adjust command generation based on previous execution errors.

---

## Capabilities
- Analyze previous errors
- Modify commands accordingly
- Retry with improved approach

---

## How to Think
- Learn from failure
- Do not repeat the same mistake
- Try alternative approaches

---

## Rules
- MUST consider previous errors
- DO NOT repeat failed commands unchanged

---

## When to Use
- When retrying tasks
- When errors are present in context

---

## When NOT to Use
- On first attempt

---

## Output Expectations
- Improved commands

---

## Output Format
Same as command_generation

---

## Failure Modes
- Repeating failing commands
- Overcorrecting unnecessarily

---

## Examples

### Input
Error: command not found

### Output
{
  "commands": [
    {"cmd": "<native package manager> install tool", "risk": "medium"}
  ]
}
