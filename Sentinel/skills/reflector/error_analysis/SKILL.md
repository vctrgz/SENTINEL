# Skill: error_analysis

## Description
Analyze execution outputs and identify errors, warnings, or anomalies.

---

## Capabilities
- Parse command outputs (stdout, stderr)
- Detect known error patterns
- Extract meaningful error messages

---

## How to Think
- Focus on factual output, not assumptions
- Prioritize stderr over stdout for errors
- Identify root cause, not just symptoms

---

## Rules
- DO NOT invent errors
- DO NOT ignore stderr
- MUST extract the most relevant issue

---

## When to Use
- After command execution
- When analyzing logs

---

## When NOT to Use
- Before execution
- When no output is available

---

## Output Expectations
- Clear identification of error or success

---

## Output Format
{
  "error_detected": true|false,
  "error_type": "string",
  "message": "string"
}

---

## Failure Modes
- Missing hidden errors
- Misinterpreting warnings as failures

---

## Examples

### Input
stderr: "command not found"

### Output
{
  "error_detected": true,
  "error_type": "missing_command",
  "message": "command not found"
}