# Skill: parallelization_strategy

## Description
Decide which tasks can be executed in parallel and which must be sequential.

---

## Capabilities
- Identify independent tasks
- Assign execution modes

---

## How to Think
- If tasks do not share data → parallel
- If tasks modify shared resources → sequential
- If task is critical → exclusive

---

## Rules
- Maximize parallel execution safely
- Avoid parallel execution for destructive tasks

---

## When to Use
- After dependency analysis

---

## Output Expectations
Tasks with execution mode

---

## Output Format
"mode": "parallel|sequential|exclusive"

---

## Failure Modes
- Unsafe parallelism
- Over-sequentialization