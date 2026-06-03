# Skill: execution_preparation

## Description
Prepare validated commands for execution by structuring them for downstream systems.

---

## Capabilities
- Combine validated and approved commands
- Structure final execution payload
- Ensure compatibility with executor

---

## How to Think
- Only approved commands should reach execution
- Maintain order when required
- Keep structure clean

---

## Rules
- DO NOT include blocked commands
- DO NOT include unapproved commands
- MUST follow executor format

---

## When to Use
- Right before sending to TaskRouter

---

## When NOT to Use
- Before validation or confirmation

---

## Output Expectations
- Final execution-ready commands

---

## Output Format
{
  "commands": [
    {"cmd": "string"}
  ]
}

---

## Failure Modes
- Including unsafe commands
- Missing commands

---

## Examples

### Output
{
  "commands": [
    {"cmd": "ls"}
  ]
}