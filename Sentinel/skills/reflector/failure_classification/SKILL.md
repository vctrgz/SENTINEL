# Skill: failure_classification

## Description
Classify execution results into success, retryable failure, or fatal failure.

---

## Capabilities
- Determine severity of errors
- Decide if retry is possible

---

## How to Think
- Prefer retry if fix is possible
- Fatal = cannot be fixed automatically
- Success = no relevant errors

---

## Rules
- MUST classify every result
- DO NOT leave status undefined

---

## When to Use
- After error analysis

---

## Output Expectations
{
  "status": "success|retry|fatal"
}

---

## Failure Modes
- Misclassifying fatal as retry
- Overusing retry

---

## Examples

### Input
missing_command

### Output
{
  "status": "retry"
}