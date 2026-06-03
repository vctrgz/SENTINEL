# Skill: tool_detection

## Description
Detect when a required tool is missing and suggest installation.

---

## Capabilities
- Identify missing tools from context
- Suggest installation commands

---

## How to Think
- If command fails due to missing tool → fix it
- Prefer installing over failing

---

## Rules
- Only suggest installation if necessary
- Use standard package managers

---

## When to Use
- When command fails due to missing tool

---

## When NOT to Use
- When tool is already available

---

## Output Expectations
- Commands including installation if needed

---

## Output Format
Same as command_generation

---

## Failure Modes
- Installing unnecessary tools
- Wrong package name

---

## Examples

### Input
"nginx not found"

### Output
{
  "commands": [
    {"cmd": "<native package manager> install nginx", "risk": "high"}
  ]
}
