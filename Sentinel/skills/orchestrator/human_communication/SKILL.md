# Skill: human_communication

## Description
Explain system actions and results in clear, user-friendly language.

---

## Capabilities
- Translate technical operations into plain language
- Summarize execution steps
- Present outputs clearly

---

## How to Think
- Assume the user is not technical
- Clarity over precision
- Avoid unnecessary detail

---

## Rules
- DO NOT use technical jargon unless necessary
- Keep explanations concise
- Focus on what matters to the user

---

## When to Use
- When presenting results
- When explaining system behavior
- During HITL interactions

---

## When NOT to Use
- When structured JSON is required
- When communicating with other agents

---

## Output Expectations
- Natural language explanation

---

## Output Format
Plain text

---

## Failure Modes
- Too technical → user confusion
- Too vague → lack of understanding

---

## Examples

### Input
[{"cmd": "ls"}]

### Output
"Voy a listar los archivos del directorio actual."