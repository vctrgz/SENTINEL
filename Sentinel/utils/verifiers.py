from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.execution_state import TaskExecutionState


@dataclass
class VerificationIssue:
    verifier_type: str
    passed: bool
    details: str


@dataclass
class VerificationReport:
    passed: bool
    issues: list[VerificationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [issue.__dict__ for issue in self.issues],
        }

    @property
    def summary(self) -> str:
        if self.passed:
            return "all deterministic verifiers passed"
        failures = [issue.details for issue in self.issues if not issue.passed]
        return "; ".join(failures) if failures else "deterministic verification failed"


def _shell_results(results: list[dict]) -> list[dict]:
    return [item for item in results if isinstance(item, dict) and item.get("command") is not None]


def _tool_results(results: list[dict]) -> list[dict]:
    return [item for item in results if isinstance(item, dict) and item.get("kind") == "tool"]


def _verify_action_success(results: list[dict]) -> VerificationIssue:
    if not results:
        return VerificationIssue("action_success", False, "no action results captured")

    failures = []
    for item in results:
        if item.get("kind") == "tool":
            if item.get("success") is not True:
                failures.append(f"tool `{item.get('tool_name', item.get('tool', 'unknown'))}` failed")
        else:
            if int(item.get("returncode", 0) or 0) != 0:
                failures.append(f"shell command failed: {item.get('command', '')}")

    if failures:
        return VerificationIssue("action_success", False, "; ".join(failures))
    return VerificationIssue("action_success", True, "all actions completed successfully")


def _verify_shell_exit_code_zero(results: list[dict]) -> VerificationIssue:
    shells = _shell_results(results)
    if not shells:
        return VerificationIssue("shell_exit_code_zero", True, "no shell commands executed")
    failures = [item.get("command", "") for item in shells if int(item.get("returncode", 0) or 0) != 0]
    if failures:
        return VerificationIssue("shell_exit_code_zero", False, f"shell commands with non-zero exit code: {failures}")
    return VerificationIssue("shell_exit_code_zero", True, "all shell commands exited with code zero")


def _verify_file_changed(state: TaskExecutionState, spec: dict) -> VerificationIssue:
    min_count = int(spec.get("min_count", 1) or 1)
    count = len(state.touched_files)
    if count >= min_count:
        return VerificationIssue("file_changed", True, f"{count} file(s) changed")
    return VerificationIssue("file_changed", False, f"expected at least {min_count} changed file(s), found {count}")


def _verify_file_exists(spec: dict) -> VerificationIssue:
    import os

    path = str(spec.get("path", "") or "")
    if not path:
        return VerificationIssue("file_exists", False, "file_exists verifier missing path")
    exists = os.path.exists(path)
    return VerificationIssue("file_exists", exists, f"path `{path}` exists" if exists else f"path `{path}` does not exist")


def _verify_file_contains(spec: dict) -> VerificationIssue:
    from utils.execution_state import safe_read_text

    path = str(spec.get("path", "") or "")
    needle = str(spec.get("contains", "") or "")
    if not path or not needle:
        return VerificationIssue("file_contains", False, "file_contains verifier missing path or contains")
    content = safe_read_text(path)
    if content is None:
        return VerificationIssue("file_contains", False, f"file `{path}` could not be read")
    passed = needle in content
    return VerificationIssue("file_contains", passed, f"`{needle}` found in `{path}`" if passed else f"`{needle}` not found in `{path}`")


def _verify_search_code_results(results: list[dict], spec: dict) -> VerificationIssue:
    min_matches = int(spec.get("min_matches", 1) or 1)
    matches = 0
    for item in _tool_results(results):
        if item.get("tool_name") != "search_code":
            continue
        text = str(item.get("result", "") or "")
        if text and text.strip() and text.strip() != "(Sin resultados)":
            matches += len([line for line in text.splitlines() if line.strip()])
    if matches >= min_matches:
        return VerificationIssue("search_code_results", True, f"search_code produced {matches} line(s)")
    return VerificationIssue("search_code_results", False, f"search_code produced {matches} line(s), expected >= {min_matches}")


def run_verifiers(state: TaskExecutionState, results: list[dict], specs: list[dict] | None = None) -> VerificationReport:
    specs = specs or [{"type": "action_success"}]
    issues: list[VerificationIssue] = []

    for spec in specs:
        verifier_type = str(spec.get("type", "action_success"))
        if verifier_type == "action_success":
            issue = _verify_action_success(results)
        elif verifier_type == "shell_exit_code_zero":
            issue = _verify_shell_exit_code_zero(results)
        elif verifier_type == "file_changed":
            issue = _verify_file_changed(state, spec)
        elif verifier_type == "file_exists":
            issue = _verify_file_exists(spec)
        elif verifier_type == "file_contains":
            issue = _verify_file_contains(spec)
        elif verifier_type == "search_code_results":
            issue = _verify_search_code_results(results, spec)
        else:
            issue = VerificationIssue(verifier_type, False, f"unknown verifier type: {verifier_type}")

        issues.append(issue)
        state.record_verification(issue.verifier_type, issue.passed, issue.details)

    passed = all(issue.passed for issue in issues)
    return VerificationReport(passed=passed, issues=issues)


def infer_verification_specs(task: dict, approved_actions: list[dict]) -> list[dict]:
    specs = task.get("verification")
    inferred = list(specs) if isinstance(specs, list) and specs else [{"type": "action_success"}]
    existing_types = {str(item.get("type")) for item in inferred if isinstance(item, dict)}

    if any(action.get("cmd") for action in approved_actions):
        if any(
            any(token in str(action.get("cmd", "")).lower() for token in ("pytest", "unittest", "nose", "tox", "make test", "npm test"))
            for action in approved_actions
        ):
            if "shell_exit_code_zero" not in existing_types:
                inferred.append({"type": "shell_exit_code_zero"})
    if any(action.get("tool") in {"str_replace", "write_file"} for action in approved_actions):
        if "file_changed" not in existing_types:
            inferred.append({"type": "file_changed", "min_count": 1})
    if any(action.get("tool") == "search_code" for action in approved_actions):
        if "search_code_results" not in existing_types:
            inferred.append({"type": "search_code_results", "min_matches": 1})
    return inferred
