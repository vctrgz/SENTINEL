# Skill: task_decomposition

## Description
Break down an objective into atomic and executable tasks.

---

## Capabilities
- Split complex objectives into smaller steps
- Ensure tasks are independently executable when possible
- Minimize implicit dependencies

---

## How to Think
- Prefer independent tasks → enables parallel execution
- Only create dependencies when strictly necessary
- Smaller tasks are better than complex ones

---

## Rules
- Each task MUST be atomic
- Tasks MUST be clearly described
- DO NOT generate commands

---

## When to Use
- Always when planning tasks

---

## Output Expectations
List of tasks

---

## Failure Modes
- Tasks too large → reduce granularity
- Hidden dependencies → must be explicit