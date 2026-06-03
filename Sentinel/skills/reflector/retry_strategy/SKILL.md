# Skill: retry_strategy

## Description
Generate guidance for retrying failed tasks.

---

## Capabilities
- Suggest alternative approaches
- Modify execution strategy

---

## How to Think
- Fix root cause, not symptoms
- Try minimal changes first
- Avoid repeating same failure

---

## Rules
- DO NOT repeat identical commands
- MUST address the error cause

---

## When to Use
- When failure is retryable

---

## Output Expectations
{
  "action": "string",
  "hint": "string"
}

---

## Failure Modes
- Suggesting same failing approach
- Overcomplicating solution

---

## Examples

### Input
missing_command

### Output
{
  "action": "install_missing_tool",
  "hint": "install required package"
}