# Skill: batch_optimization

## Description
Group compatible commands for efficient execution.

---

## Capabilities
- Merge similar commands
- Reduce execution overhead

---

## How to Think
- Group commands with same executor
- Avoid unnecessary fragmentation

---

## Rules
- DO NOT merge incompatible commands
- Preserve execution order if needed

---

## Output Format
{
  "batches": [
    {
      "executor": "string",
      "commands": []
    }
  ]
}