import json
from typing import Optional

from app.config import Config
from utils.language_context import build_language_context
from utils.ollama_client import OllamaClient
from utils.json_parser import safe_json_parse
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


def _clip_text(value: str, limit: int = 400) -> str:
    if not isinstance(value, str):
        value = str(value)
    return value if len(value) <= limit else value[:limit] + "...[truncado]"


def _summarize_result(result) -> dict:
    if isinstance(result, dict):
        summary = {}
        for key in ("command", "returncode", "status", "reason", "sandbox", "tool", "installed"):
            if key in result:
                summary[key] = result[key]
        if "stdout" in result:
            summary["stdout"] = _clip_text(result["stdout"])
        if "stderr" in result:
            summary["stderr"] = _clip_text(result["stderr"])
        if "error" in result:
            summary["error"] = _clip_text(result["error"])
        if "result" in result and "result" not in summary:
            summary["result"] = _clip_text(result["result"])
        return summary

    if isinstance(result, list):
        return {"items": [_summarize_result(item) for item in result[:5]], "count": len(result)}

    return {"value": _clip_text(str(result))}


class ReflectorAgent:
    def __init__(self):
        OLLAMA_MODEL = Config.MODELS.get(Config.DEFAULT_MODEL, "balanceado")
        self.llm = OllamaClient(OLLAMA_MODEL)
        self.system_prompt = build_system_prompt("agents/reflector")

    def run(self, execution_results: list, task: Optional[dict] = None) -> dict:
        summarized_results = [_summarize_result(result) for result in execution_results[:10]]
        summarized_task = {
            "task_id": (task or {}).get("task_id", ""),
            "objective": (task or {}).get("objective", ""),
            "priority": (task or {}).get("priority", ""),
            "context": self.llm.context_manager.prepare_task_context(task or {"context": {}}),
        }
        language_context = summarized_task["context"].get("language") or build_language_context(summarized_task["objective"])

        user_prompt = f"""
{build_runtime_context_block(language_context=language_context)}

Execution Results:
{json.dumps(summarized_results, ensure_ascii=False)}

Task:
{json.dumps(summarized_task, ensure_ascii=False)}
"""

        response = self.llm.chat(self.system_prompt, user_prompt, expect_json=True)
        return safe_json_parse(response)
