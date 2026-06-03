from __future__ import annotations

import re
from copy import deepcopy

_INSPECT_PATTERNS = (
    r"\binspect\b",
    r"\bexplore\b",
    r"\banaly[sz]e\b",
    r"\bscan\b",
    r"\blist\b",
    r"\bstructure\b",
    r"\brepo\b",
    r"\bdirectory\b",
    r"\bbusca(?:r)?\b",
    r"\blista(?:r)?\b",
    r"\bexplora(?:r)?\b",
    r"\banaliza(?:r)?\b",
)

_READ_PATTERNS = (
    r"\bread\b",
    r"\bopen\b",
    r"\bshow\b",
    r"\bview\b",
    r"\bfile\b",
    r"\bsource\b",
    r"\breadme\b",
    r"\blee(?:r)?\b",
    r"\barchivo(?:s)?\b",
    r"\bcodigo\b",
)

_EDIT_PATTERNS = (
    r"\bedit\b",
    r"\bmodify\b",
    r"\bupdate\b",
    r"\bchange\b",
    r"\bpatch\b",
    r"\bfix\b",
    r"\bcreate\b",
    r"\bwrite\b",
    r"\breplace\b",
    r"\bimplement\b",
    r"\brefactor\b",
    r"\bedita(?:r)?\b",
    r"\bmodifica(?:r)?\b",
    r"\bactualiza(?:r)?\b",
    r"\bcambia(?:r)?\b",
    r"\barregla(?:r)?\b",
    r"\bcrea(?:r)?\b",
    r"\breemplaza(?:r)?\b",
    r"\bimplementa(?:r)?\b",
)

_VALIDATE_PATTERNS = (
    r"\btest(?:s)?\b",
    r"\bpytest\b",
    r"\bvalidate\b",
    r"\bverify\b",
    r"\bcheck\b",
    r"\blint\b",
    r"\bbuild\b",
    r"\brun\b",
    r"\bejecuta(?:r)?\b",
    r"\bprueba(?:s)?\b",
    r"\bvalida(?:r)?\b",
    r"\bverifica(?:r)?\b",
    r"\bcompila(?:r)?\b",
)

_PARALLEL_SAFE_INTENTS = {"inspect_repo", "read_source"}
_READ_ONLY_VERIFIER_TYPES = {"file_exists", "file_contains", "search_code_results"}
_MUTATING_VALIDATION_PATTERNS = (
    r"\bpytest\b",
    r"\btest(?:s)?\b",
    r"\bnpm test\b",
    r"\bmake test\b",
    r"\btox\b",
    r"\blint\b",
    r"\bbuild\b",
    r"\bcompile\b",
    r"\brun\b",
    r"\bejecuta(?:r)?\b",
    r"\bprueba(?:s)?\b",
    r"\bcompila(?:r)?\b",
)


def _has_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def infer_task_intent(task: dict, objective: str = "") -> str:
    text = "\n".join(
        str(part)
        for part in (
            task.get("description", ""),
            task.get("objective", ""),
            objective,
            task.get("phase", ""),
        )
        if part
    )
    normalized = text.lower()

    if _has_any(_EDIT_PATTERNS, normalized):
        return "edit_source"
    if _has_any(_VALIDATE_PATTERNS, normalized):
        return "run_validation"
    if _has_any(_READ_PATTERNS, normalized):
        return "read_source"
    if _has_any(_INSPECT_PATTERNS, normalized):
        return "inspect_repo"
    return "general"


def default_verification_for_intent(intent: str) -> list[dict]:
    if intent == "edit_source":
        return [
            {"type": "action_success"},
            {"type": "file_changed", "min_count": 1},
        ]
    if intent == "run_validation":
        return [
            {"type": "action_success"},
            {"type": "shell_exit_code_zero"},
        ]
    if intent in {"inspect_repo", "read_source"}:
        return [{"type": "action_success"}]
    return [{"type": "action_success"}]


def is_read_only_validation_task(task: dict) -> bool:
    if not isinstance(task, dict):
        return False
    if str(task.get("intent", "")).lower() != "run_validation":
        return False

    specs = task.get("verification", [])
    if not isinstance(specs, list) or not specs:
        return False

    verifier_types = {
        str(item.get("type", "")).lower()
        for item in specs
        if isinstance(item, dict) and item.get("type")
    }
    if not verifier_types:
        return False
    if not verifier_types.issubset(_READ_ONLY_VERIFIER_TYPES):
        return False

    description = "\n".join(
        str(part)
        for part in (
            task.get("description", ""),
            task.get("objective", ""),
            task.get("phase", ""),
        )
        if part
    ).lower()
    if _has_any(_MUTATING_VALIDATION_PATTERNS, description):
        return False

    return True


def is_parallel_safe_task(task: dict) -> bool:
    if not isinstance(task, dict):
        return False
    if task.get("parallel_safe") is True:
        return True
    if task.get("mode") == "exclusive":
        return False
    if task.get("requires_replan"):
        return False
    intent = str(task.get("intent", "")).lower()
    if intent in _PARALLEL_SAFE_INTENTS:
        return True
    if is_read_only_validation_task(task):
        return True
    return False


def enrich_plan_tasks(plan: dict, objective: str = "") -> dict:
    enriched = deepcopy(plan or {})
    tasks = enriched.get("tasks", [])
    if not isinstance(tasks, list):
        enriched["tasks"] = []
        return enriched

    for task in tasks:
        if not isinstance(task, dict):
            continue
        intent = task.get("intent") or infer_task_intent(task, objective)
        task["intent"] = intent
        task.setdefault("objective", objective)
        task.setdefault("max_cycles", 3 if intent == "edit_source" else 2)
        task.setdefault("verification", default_verification_for_intent(intent))
        task.setdefault("parallel_safe", is_parallel_safe_task(task))

    return enriched
