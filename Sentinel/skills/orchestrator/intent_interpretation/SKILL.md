name: intent_interpretation

# Skill: intent_interpretation

## Description
Convert raw user input into a clear, explicit, and actionable objective.

---

## Capabilities
- Identify user intent from natural language
- Extract the primary goal
- Filter irrelevant or noisy information
- Normalize vague expressions into concrete objectives

---

## How to Think
- Focus on WHAT the user wants, not HOW to do it
- Prefer clarity over completeness
- Do not assume hidden intentions
- If ambiguity is high, flag it instead of guessing

---

## Rules
- The objective MUST be concise and actionable
- DO NOT include implementation details
- DO NOT generate commands
- DO NOT invent missing information

---

## When to Use
- When receiving raw user input
- When input is ambiguous or unstructured
- At the start of the task lifecycle

---

## When NOT to Use
- When the objective is already clearly defined
- When working with structured data

---

## Output Expectations
- A single clear objective string

---

## Output Format
"objective": "string"

---

## Failure Modes
- If multiple interpretations exist → return the most probable and note ambiguity
- If input is too vague → request clarification

---

## Examples

### Input
"quiero ver los archivos de esta carpeta"

### Output
"listar los archivos del directorio actual"

---

### Input
"haz algo con nginx"

### Output
"objetivo ambiguo: el usuario no especifica acción concreta"