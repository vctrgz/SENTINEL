# Skill: dependency_analysis

## Description
Determine dependencies between tasks to ensure correct execution order.

---

## Capabilities
- Identify task relationships
- Build dependency graph (DAG)

---

## How to Think
- A task depends on another ONLY if it requires its output
- Avoid unnecessary dependencies → enables parallelism

---

## Rules
- Dependencies MUST be explicit
- DO NOT create circular dependencies

---

## When to Use
- After task decomposition

---

## Output Expectations
Tasks with depends_on field

---

## Output Format
"depends_on": [task_ids]

---

## Failure Modes
- Missing dependencies → race conditions
- Too many dependencies → no parallelism