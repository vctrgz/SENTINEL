import json
from app.config import Config
from utils.command_validator import CommandValidator
from utils.language_context import build_language_context
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from utils.tool_registry import build_default_registry


class TranslatorAgent:

    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, 'balanceado')
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.validator = CommandValidator()
        self.tool_registry = build_default_registry()
        self.system_prompt = build_system_prompt("agents/translator")

    def validate_commands(self, commands: list) -> list:

        validated = []

        for cmd_obj in commands:
            cmd = cmd_obj["cmd"]

            result = self.validator.validate(cmd)

            cmd_obj["validation"] = result

            validated.append(cmd_obj)

        return validated

    def _normalize_actions(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"actions": []}

        actions = payload.get("actions")
        if isinstance(actions, list):
            normalized = []
            for item in actions:
                if not isinstance(item, dict):
                    continue
                kind = item.get("kind")
                if kind == "tool" and item.get("tool"):
                    normalized.append({
                        "kind": "tool",
                        "tool": item.get("tool", ""),
                        "params": item.get("params", {}) if isinstance(item.get("params"), dict) else {},
                        "risk": item.get("risk", "low"),
                    })
                elif item.get("cmd"):
                    normalized.append({
                        "kind": "shell",
                        "cmd": item.get("cmd", ""),
                        "risk": item.get("risk", "low"),
                    })
            return {"actions": normalized}

        commands = payload.get("commands", [])
        normalized = []
        if isinstance(commands, list):
            for item in commands:
                if isinstance(item, dict) and item.get("cmd"):
                    normalized.append({
                        "kind": "shell",
                        "cmd": item.get("cmd", ""),
                        "risk": item.get("risk", "low"),
                    })
        return {"actions": normalized}
    
    def run(self, plan: dict, context: dict) -> dict:
        compact_context = self.llm.context_manager._truncate_context(context)
        language_context = compact_context.get("language") or build_language_context(json.dumps(plan.get('tasks', []), ensure_ascii=False))
        tools_block = self.tool_registry.schemas_as_prompt()

        user_prompt = f"""
{build_runtime_context_block(language_context=language_context)}

Available deterministic tools:
{tools_block}

Tasks:
{json.dumps(plan.get('tasks', []), ensure_ascii=False)}

Context:
{json.dumps(compact_context, ensure_ascii=False)}

Return ONLY valid JSON with this schema:
{{
  "actions": [
    {{
      "kind": "shell",
      "cmd": "string",
      "risk": "low|medium|high"
    }},
    {{
      "kind": "tool",
      "tool": "string",
      "params": {{}},
      "risk": "low|medium|high"
    }}
  ]
}}
"""

        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)
        try:
            return self._normalize_actions(safe_json_parse(response))
        except ValueError:
            repair_prompt = f"""
{build_runtime_context_block(language_context=language_context)}

Convert the following response into valid JSON only.

Required schema:
{{
  "actions": [
    {{
      "kind": "shell",
      "cmd": "string",
      "risk": "low|medium|high"
    }},
    {{
      "kind": "tool",
      "tool": "string",
      "params": {{}},
      "risk": "low|medium|high"
    }}
  ]
}}

Original response:
{response}
"""
            repaired = self.llm.chat(self.system_prompt, repair_prompt, expect_json=True)
            return self._normalize_actions(safe_json_parse(repaired))
