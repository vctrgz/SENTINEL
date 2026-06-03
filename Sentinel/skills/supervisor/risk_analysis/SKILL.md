# Skill: risk_analysis

## Description
Analyze commands to determine their risk level and potential impact on the system.

---

## Capabilities
- Detect destructive or irreversible operations
- Identify system-wide changes
- Evaluate potential side effects of commands

---

## How to Think
- Assume worst-case scenario
- A command is dangerous if it modifies, deletes, or installs system components
- Read-only operations are generally low risk

---

## Rules
- MUST evaluate every command
- DO NOT ignore command flags or arguments
- DO NOT assume commands are safe

---

## When to Use
- Before any command execution
- After Translator generates commands

---

## When NOT to Use
- When working with non-executable data
- After execution has already occurred

---

## Output Expectations
- Risk classification for each command

---

## Output Format
{
  "commands": [
    {
      "cmd": "string",
      "risk": "low|medium|high",
      "reason": "string"
    }
  ]
}

---

## Failure Modes
- Underestimating risk → dangerous execution
- Overestimating risk → unnecessary friction

---

## Examples

### Input
"rm test.txt"

### Output
{
  "commands": [
    {
      "cmd": "rm test.txt",
      "risk": "medium",
      "reason": "Deletes a file"
    }
  ]
}