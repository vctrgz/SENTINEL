# Skill: plan_structuring

## Description
Build the final execution plan in DAG format.

---

## Capabilities
- Combine tasks, dependencies, and execution modes
- Produce structured plan

---

## How to Think
- Plan must be deterministic
- Structure must be clean and minimal

---

## Rules
- MUST follow JSON format strictly
- Include id, description, depends_on, mode

---

## Output Format
{
  "tasks": [
    {
      "id": 1,
      "description": "string",
      "depends_on": [],
      "mode": "parallel|sequential|exclusive"
    }
  ]
}

---

## Failure Modes
- Invalid JSON
- Missing fields