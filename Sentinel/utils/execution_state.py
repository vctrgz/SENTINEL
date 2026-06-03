from __future__ import annotations

import difflib
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ActionRecord:
    phase: str
    action: dict
    result: dict
    started_at: float
    finished_at: float

    @property
    def duration_s(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["duration_s"] = self.duration_s
        return data


@dataclass
class DiffRecord:
    path: str
    before: str
    after: str
    diff: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "before_len": len(self.before),
            "after_len": len(self.after),
            "diff": self.diff,
        }


@dataclass
class VerificationRecord:
    verifier_type: str
    passed: bool
    details: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskExecutionState:
    task_id: str
    description: str
    intent: str
    status: str = "pending"
    current_cycle: int = 0
    phases_completed: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    shell_commands: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    diffs: list[DiffRecord] = field(default_factory=list)
    action_history: list[ActionRecord] = field(default_factory=list)
    verification_history: list[VerificationRecord] = field(default_factory=list)
    last_failure: str = ""

    def begin_cycle(self) -> None:
        self.current_cycle += 1

    def mark_phase(self, phase: str) -> None:
        if phase not in self.phases_completed:
            self.phases_completed.append(phase)

    def record_action(self, phase: str, action: dict, result: dict, started_at: float, finished_at: float) -> None:
        self.action_history.append(ActionRecord(
            phase=phase,
            action=action,
            result=result,
            started_at=started_at,
            finished_at=finished_at,
        ))
        if action.get("kind") == "tool":
            self.tool_calls.append({
                "phase": phase,
                "tool": action.get("tool", ""),
                "params": action.get("params", {}),
            })
        elif action.get("cmd"):
            self.shell_commands.append(action["cmd"])

    def record_diff(self, path: str, before: str, after: str) -> None:
        if path not in self.touched_files:
            self.touched_files.append(path)
        diff = "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        self.diffs.append(DiffRecord(path=path, before=before, after=after, diff=diff))

    def record_artifact(self, name: str, value: Any, category: str = "generic") -> None:
        self.artifacts.append({
            "name": name,
            "category": category,
            "value": value,
        })

    def record_verification(self, verifier_type: str, passed: bool, details: str) -> None:
        self.verification_history.append(VerificationRecord(
            verifier_type=verifier_type,
            passed=passed,
            details=details,
        ))
        if not passed:
            self.last_failure = details

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "intent": self.intent,
            "status": self.status,
            "current_cycle": self.current_cycle,
            "phases_completed": list(self.phases_completed),
            "touched_files": list(self.touched_files),
            "shell_commands": list(self.shell_commands),
            "tool_calls": list(self.tool_calls),
            "artifacts": list(self.artifacts),
            "diffs": [item.to_dict() for item in self.diffs],
            "action_history": [item.to_dict() for item in self.action_history],
            "verification_history": [item.to_dict() for item in self.verification_history],
            "last_failure": self.last_failure,
        }


def safe_read_text(path: str) -> str | None:
    try:
        if not path or not os.path.exists(path) or not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return None


def tool_target_paths(action: dict) -> list[str]:
    params = action.get("params", {}) if isinstance(action, dict) else {}
    if not isinstance(params, dict):
        return []
    paths: list[str] = []
    for key in ("path",):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value)
    return paths


def capture_file_snapshots(action: dict) -> dict[str, str | None]:
    snapshots: dict[str, str | None] = {}
    for path in tool_target_paths(action):
        snapshots[path] = safe_read_text(path)
    return snapshots


def finalize_file_snapshots(state: TaskExecutionState, before: dict[str, str | None], action: dict) -> None:
    for path in tool_target_paths(action):
        previous = before.get(path)
        current = safe_read_text(path)
        if current is None and previous is None:
            continue
        if current != previous:
            state.record_diff(path, previous or "", current or "")


def now_ts() -> float:
    return time.time()
