# Skill: multi_phase_recon

## Description
Plan multi-phase network reconnaissance tasks with dynamic host-injection between phases.

---

## Core Principle: Phased Recon
Network recon CANNOT be planned as a single flat list of tasks.
It requires a **hierarchical, phased approach** where Phase 2 tasks are
generated dynamically based on the results of Phase 1.

---

## Standard Recon Plan Structure

### Phase 1: Environment Setup & Discovery (tasks 1-2)
- Task 1: Detect local network CIDR (ip addr, ip route)
- Task 2: Run host discovery sweep (nmap -sn <CIDR>)
  - mode: sequential
  - depends_on: [1]

### Phase 2: Per-Host Enumeration (tasks 3-N, DYNAMIC)
- For each discovered host, create ONE task:
  - description: "Port scan and service detection on <ip>"
  - mode: parallel (all hosts can be scanned simultaneously)
  - depends_on: [2]
- ⚠️ These tasks are created AFTER Phase 1 results are parsed.

### Phase 3: Aggregation & Report (last task)
- description: "Aggregate all scan results into a structured network map"
- mode: sequential
- depends_on: [all Phase 2 task IDs]

---

## When "Gather info on all network devices" is requested:

You MUST create this plan structure:

```json
{
  "tasks": [
    {
      "id": 1,
      "description": "Detect local network CIDR and interface information",
      "depends_on": [],
      "mode": "parallel"
    },
    {
      "id": 2,
      "description": "Run network host discovery sweep on detected CIDR to find all live hosts",
      "depends_on": [1],
      "mode": "sequential",
      "phase": "discovery",
      "requires_replan": true
    },
    {
      "id": 3,
      "description": "Deep port scan and service/OS detection on each discovered host",
      "depends_on": [2],
      "mode": "parallel",
      "phase": "enumeration",
      "dynamic": true
    },
    {
      "id": 4,
      "description": "Compile all gathered information into a comprehensive network topology report",
      "depends_on": [3],
      "mode": "sequential",
      "phase": "synthesis"
    }
  ]
}
```

---

## Key Fields
- `phase`: "discovery" | "enumeration" | "synthesis"
- `requires_replan`: true on discovery tasks → triggers dynamic host injection
- `dynamic`: true on per-host tasks → one task instance per discovered host

---

## Rules
- NEVER plan per-host scans without a prior discovery task
- ALWAYS include a synthesis/aggregation task at the end
- Enumeration tasks MUST be parallel (independent per host)
- Discovery task MUST be sequential (single sweep)
- DO NOT assume you know the hosts ahead of time

---

## Failure Modes
- Flat planning (all commands in one task) → too coarse, no parallelism
- Skipping discovery → misses uncached hosts
- No synthesis task → results scattered, not actionable