# Skill: executor_selection

## Description
Select the appropriate executor agent for each command.

---

## Capabilities
- Map command types to executors
- Optimize distribution of workload

---

## How to Think
- Each executor has a specialization
- Prefer specialized executor over generic

---

## Rules
- MUST assign an executor
- DO NOT assign multiple executors to one command

---

## Output Format
{
  "routing": [
    {
      "cmd": "string",
      "executor": "shell|tool_manager|api_executor"
    }
  ]
}