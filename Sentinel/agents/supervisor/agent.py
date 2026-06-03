import json
from app.config import Config
from utils.command_validator import CommandValidator
from utils.language_context import build_language_context
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


_TOOL_RISK_DEFAULTS = {
    "read_file": "low",
    "list_directory": "low",
    "search_code": "low",
    "str_replace": "medium",
    "write_file": "medium",
    "bash": "high",
}

_INSTALL_COMMAND_MARKERS = (
    "winget install",
    "choco install",
    "brew install",
    "apt install",
    "apt-get install",
    "pip install",
    "pip3 install",
    "npm install",
)


class SupervisorAgent:

    def __init__(self) -> None:
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, "qwen2.5:latest")
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.validator = CommandValidator()
        self.system_prompt = build_system_prompt("agents/supervisor")

    def _normalize_actions(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"approved": [], "needs_confirmation": []}

        approved = payload.get("approved", [])
        needs_confirmation = payload.get("needs_confirmation", [])

        if not approved and "commands" in payload:
            approved = payload.get("commands", [])

        normalized_approved = []
        for item in approved if isinstance(approved, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("kind") == "tool" and item.get("tool"):
                normalized_approved.append({
                    "kind": "tool",
                    "tool": item.get("tool", ""),
                    "params": item.get("params", {}) if isinstance(item.get("params"), dict) else {},
                    "risk": item.get("risk", _TOOL_RISK_DEFAULTS.get(item.get("tool", ""), "medium")),
                })
            elif item.get("cmd"):
                normalized_approved.append({
                    "kind": "shell",
                    "cmd": item.get("cmd", ""),
                    "risk": item.get("risk", "medium"),
                })

        normalized_confirmation = []
        for item in needs_confirmation if isinstance(needs_confirmation, list) else []:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            if not entry.get("kind"):
                entry["kind"] = "tool" if entry.get("tool") else "shell"
            normalized_confirmation.append(entry)

        return {"approved": normalized_approved, "needs_confirmation": normalized_confirmation}

    def _deterministic_gate(self, actions: list[dict], objective: str = "") -> dict:
        approved: list[dict] = []
        needs_confirmation: list[dict] = []
        normalized_objective = (objective or "").lower()
        install_explicitly_requested = any(
            token in normalized_objective
            for token in ("install", "instalar", "setup", "configurar", "configure")
        )

        for item in actions:
            if not isinstance(item, dict):
                continue

            if item.get("kind") == "tool" and item.get("tool"):
                risk = item.get("risk", _TOOL_RISK_DEFAULTS.get(item["tool"], "medium"))
                candidate = {
                    "kind": "tool",
                    "tool": item.get("tool", ""),
                    "params": item.get("params", {}) if isinstance(item.get("params"), dict) else {},
                    "risk": risk,
                }
                if risk == "high":
                    candidate["reason"] = f"tool action `{item['tool']}` can modify repository state"
                    needs_confirmation.append(candidate)
                else:
                    approved.append(candidate)
                continue

            cmd = item.get("cmd", "")
            if not cmd:
                continue
            normalized_cmd = cmd.lower().strip()
            if any(normalized_cmd.startswith(marker) for marker in _INSTALL_COMMAND_MARKERS) and not install_explicitly_requested:
                needs_confirmation.append({
                    "kind": "shell",
                    "cmd": cmd,
                    "risk": item.get("risk", "high"),
                    "reason": "installation command was not explicitly requested by the user",
                })
                continue
            validation = self.validator.validate(cmd)
            candidate = {
                "kind": "shell",
                "cmd": cmd,
                "risk": item.get("risk", validation.risk),
            }
            if validation.valid and validation.risk in ("low", "medium"):
                approved.append(candidate)
            else:
                candidate["reason"] = validation.reason
                needs_confirmation.append(candidate)

        return {"approved": approved, "needs_confirmation": needs_confirmation}

    def run(self, commands: dict, objective: str = "", language_context: dict | None = None) -> dict:
        language_context = language_context or build_language_context(objective or json.dumps(commands, ensure_ascii=False))
        actions = []
        if isinstance(commands, dict):
            actions = commands.get("actions") or commands.get("commands") or []

        deterministic = self._deterministic_gate(actions if isinstance(actions, list) else [], objective=objective)
        if deterministic["approved"] or deterministic["needs_confirmation"]:
            return deterministic

        user_prompt = f"""
{build_runtime_context_block(language_context=language_context)}

Objective: {objective}

Actions:
{json.dumps(commands, ensure_ascii=False)}
"""
        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)
        return self._normalize_actions(safe_json_parse(response))
