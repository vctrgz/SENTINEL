# Skill: policy_enforcement

## Description
Ensure commands comply with system safety policies and constraints.

---

## Capabilities
- Enforce security rules
- Block forbidden commands
- Apply system restrictions

---

## How to Think
- Security over functionality
- If in doubt → block or escalate
- Policies override user intent

---

## Rules
- MUST block forbidden patterns
- DO NOT allow system-critical operations without control
- ALWAYS enforce defined policies

---

## When to Use
- Before execution
- After validation

---

## When NOT to Use
- When no policies are defined

---

## Output Expectations
- Allowed and blocked commands

---

## Output Format
{
  "allowed": [],
  "blocked": [
    {
      "cmd": "string",
      "reason": "string"
    }
  ]
}

---

## Failure Modes
- Allowing forbidden commands
- Blocking safe commands unnecessarily

---

## Examples

### Input
"rm -rf /"

### Output
{
  "allowed": [],
  "blocked": [
    {
      "cmd": "rm -rf /",
      "reason": "Critical system destruction command"
    }
  ]
}