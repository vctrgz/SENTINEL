# Skill: permission_handling

## Description
Determine which commands require explicit user confirmation before execution.

---

## Capabilities
- Identify commands requiring approval
- Separate safe and unsafe operations
- Prepare confirmation requests

---

## How to Think
- High risk → always ask
- Medium risk → usually ask
- Low risk → auto-approve

---

## Rules
- MUST require confirmation for high-risk commands
- DO NOT auto-approve destructive actions
- DO NOT skip confirmation for system modifications

---

## When to Use
- After risk analysis
- Before execution

---

## When NOT to Use
- When all commands are low risk

---

## Output Expectations
- Commands split by approval status

---

## Output Format
{
  "approved": [
    {"cmd": "string"}
  ],
  "needs_confirmation": [
    {
      "cmd": "string",
      "reason": "string"
    }
  ]
}

---

## Failure Modes
- Missing critical confirmation
- Asking confirmation for trivial actions

---

## Examples

### Input
"<native package manager> install nginx"

### Output
{
  "approved": [],
  "needs_confirmation": [
    {
      "cmd": "<native package manager> install nginx",
      "reason": "Installs software on the system"
    }
  ]
}
