from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.constants import STATUS_FATAL, STATUS_RETRY, STATUS_SUCCESS
from utils.execution_state import (
    TaskExecutionState,
    capture_file_snapshots,
    finalize_file_snapshots,
    now_ts,
)
from utils.logger import logger
from utils.retry_handler import classify_error
from utils.verifiers import infer_verification_specs, run_verifiers


class TaskExecutionEngine:
    def __init__(self, router) -> None:
        self.router = router

    def execute_task(self, task: dict, translator, supervisor, context: dict) -> dict:
        task = deepcopy(task or {})
        state = TaskExecutionState(
            task_id=str(task.get("id", task.get("task_id", "unknown"))),
            description=str(task.get("description", "")),
            intent=str(task.get("intent", "general")),
        )

        intent = state.intent
        max_cycles = int(task.get("max_cycles", 3 if intent == "edit_source" else 2) or 1)

        if intent == "edit_source":
            return self._execute_edit_loop(task, translator, supervisor, context, state, max_cycles)

        result = self._execute_single_phase(task, "direct", translator, supervisor, context, state)
        verification_specs = infer_verification_specs(task, result.get("approved_actions", []))
        verification = run_verifiers(state, result.get("action_results", []), verification_specs)
        status = STATUS_SUCCESS if verification.passed else STATUS_FATAL
        result["status"] = status
        result["reason"] = verification.summary
        result["verification"] = verification.to_dict()
        return self._finalize_result(result, state)

    def _execute_edit_loop(self, task: dict, translator, supervisor, context: dict, state: TaskExecutionState, max_cycles: int) -> dict:
        all_action_results: list[dict] = []

        for cycle in range(1, max_cycles + 1):
            state.begin_cycle()
            phase_results: list[dict] = []

            if cycle == 1:
                inspect_result = self._execute_single_phase(task, "inspect", translator, supervisor, context, state)
                phase_results.extend(inspect_result.get("action_results", []))
                all_action_results.extend(inspect_result.get("action_results", []))

            main_phase = "edit" if cycle == 1 else "repair"
            main_result = self._execute_single_phase(task, main_phase, translator, supervisor, context, state)
            phase_results.extend(main_result.get("action_results", []))
            all_action_results.extend(main_result.get("action_results", []))

            validate_result = self._execute_single_phase(task, "validate", translator, supervisor, context, state)
            phase_results.extend(validate_result.get("action_results", []))
            all_action_results.extend(validate_result.get("action_results", []))

            if not validate_result.get("approved_actions"):
                state.status = STATUS_RETRY
                state.last_failure = "no validation actions were produced for the edited task"
                if cycle >= max_cycles:
                    return self._finalize_result({
                        "status": STATUS_FATAL,
                        "reason": state.last_failure,
                        "action_results": all_action_results,
                    }, state)
                continue

            verification_specs = infer_verification_specs(task, main_result.get("approved_actions", []) + validate_result.get("approved_actions", []))
            verification = run_verifiers(state, phase_results, verification_specs)
            if verification.passed:
                return self._finalize_result({
                    "status": STATUS_SUCCESS,
                    "reason": verification.summary,
                    "action_results": all_action_results,
                    "verification": verification.to_dict(),
                }, state)

            state.status = STATUS_RETRY
            state.last_failure = verification.summary
            if cycle >= max_cycles:
                return self._finalize_result({
                    "status": STATUS_FATAL,
                    "reason": verification.summary,
                    "action_results": all_action_results,
                    "verification": verification.to_dict(),
                }, state)

        return self._finalize_result({
            "status": STATUS_FATAL,
            "reason": "edit loop exhausted",
            "action_results": all_action_results,
        }, state)

    def _execute_single_phase(self, task: dict, phase: str, translator, supervisor, context: dict, state: TaskExecutionState) -> dict:
        state.mark_phase(phase)
        phase_task = self._build_phase_task(task, phase, state)
        phase_context = self._build_phase_context(context, state, phase)
        translated = translator.run({"tasks": [phase_task]}, phase_context)
        validated = supervisor.run(
            translated,
            objective=phase_task.get("description", task.get("objective", "")),
            language_context=phase_context.get("language"),
        )
        approved_actions = validated.get("approved", []) if isinstance(validated, dict) else []
        needs_confirmation = validated.get("needs_confirmation", []) if isinstance(validated, dict) else []

        if not approved_actions:
            reason = "No approved actions"
            if needs_confirmation:
                reason = f"Actions require confirmation: {needs_confirmation}"
            state.last_failure = reason
            return {
                "status": STATUS_RETRY,
                "reason": reason,
                "approved_actions": [],
                "action_results": [],
                "needs_confirmation": needs_confirmation,
            }

        action_results = self._run_approved_actions(approved_actions, phase, state)
        status = STATUS_SUCCESS if all(self._result_success(item) for item in action_results) else STATUS_RETRY
        reason = "phase completed" if status == STATUS_SUCCESS else "phase produced failing actions"
        return {
            "status": status,
            "reason": reason,
            "approved_actions": approved_actions,
            "action_results": action_results,
            "needs_confirmation": needs_confirmation,
        }

    def _run_approved_actions(self, actions: list[dict], phase: str, state: TaskExecutionState) -> list[dict]:
        results: list[dict] = []
        for action in actions:
            started = now_ts()
            before = capture_file_snapshots(action) if action.get("kind") == "tool" else {}
            try:
                batch_result = self.router.execute([action])
                result = batch_result[0] if batch_result else {"error": "empty router result"}
            except Exception as exc:
                result = {
                    "error": str(exc),
                    "kind": action.get("kind", "shell"),
                    "returncode": -1,
                    "stdout": "",
                    "stderr": str(exc),
                }
            finished = now_ts()
            if action.get("kind") == "tool":
                finalize_file_snapshots(state, before, action)
            state.record_action(phase, action, result, started, finished)
            self._capture_artifacts_from_result(state, action, result)
            results.append(result)
        return results

    def _capture_artifacts_from_result(self, state: TaskExecutionState, action: dict, result: dict) -> None:
        if action.get("kind") == "tool":
            tool_name = action.get("tool", "")
            if tool_name in {"read_file", "list_directory", "search_code"} and result.get("success"):
                state.record_artifact(tool_name, result.get("result"), category="tool_output")
        else:
            command = action.get("cmd", "")
            if result.get("stdout"):
                state.record_artifact(command or "shell", str(result.get("stdout", ""))[:2000], category="stdout")
            if result.get("stderr"):
                state.record_artifact(command or "shell", str(result.get("stderr", ""))[:1000], category="stderr")

    @staticmethod
    def _result_success(result: dict) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("kind") == "tool":
            return bool(result.get("success"))
        return int(result.get("returncode", 0) or 0) == 0

    def _build_phase_context(self, context: dict, state: TaskExecutionState, phase: str) -> dict:
        phase_context = deepcopy(context or {})
        phase_context["execution_state"] = state.to_dict()
        phase_context["execution_phase"] = phase
        phase_context["last_failure"] = state.last_failure
        return phase_context

    def _build_phase_task(self, task: dict, phase: str, state: TaskExecutionState) -> dict:
        description = str(task.get("description", ""))
        phase_task = deepcopy(task)

        if phase == "inspect":
            phase_task["intent"] = "inspect_repo"
            phase_task["description"] = (
                f"Inspect the repository and identify the exact files, directories, and symbols needed for this task: {description}. "
                "Prefer list_directory, search_code, and read_file."
            )
        elif phase == "edit":
            phase_task["intent"] = "edit_source"
            phase_task["description"] = (
                f"Apply the required source changes for this task: {description}. "
                "Prefer deterministic edits with str_replace or write_file when justified."
            )
        elif phase == "repair":
            phase_task["intent"] = "edit_source"
            phase_task["description"] = (
                f"Repair the previous failed implementation for this task: {description}. "
                f"Last deterministic failure: {state.last_failure}. "
                f"Touched files so far: {state.touched_files}."
            )
        elif phase == "validate":
            phase_task["intent"] = "run_validation"
            phase_task["description"] = (
                f"Run the narrowest deterministic validation for this task: {description}. "
                f"Focus on files: {state.touched_files or 'unknown'} and prefer targeted tests or checks."
            )
        else:
            phase_task.setdefault("intent", state.intent)

        phase_task["execution_phase"] = phase
        phase_task["verification"] = task.get("verification", [])
        phase_task["max_cycles"] = task.get("max_cycles", 2)
        return phase_task

    def _finalize_result(self, result: dict, state: TaskExecutionState) -> dict:
        final = deepcopy(result)
        status = final.get("status", STATUS_SUCCESS)
        state.status = status
        final["execution_state"] = state.to_dict()
        final.setdefault("task_id", state.task_id)
        final.setdefault("intent", state.intent)
        return final


def classify_environment_failure(reason: str) -> str:
    lowered = (reason or "").lower()
    if not lowered:
        return "unknown"
    if "timeout" in lowered:
        return "timeout"
    if "permission" in lowered or "permiso" in lowered:
        return "permission"
    if "not found" in lowered or "no encontrado" in lowered:
        return "missing_dependency"
    try:
        return classify_error(Exception(reason))
    except Exception:
        return "transient"
