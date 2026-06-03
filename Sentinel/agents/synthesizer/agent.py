import json
from typing import Any, List

from agents.web_researcher.agent import WebResearchAgent
from app.config import Config
from utils.language_context import build_language_context
from utils.logger import logger
from utils.network_analysis import render_network_markdown
from utils.network_parser import NetworkReport
from utils.ollama_client import OllamaClient
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from utils.runtime_tracer import get_tracer


def _extract_stdout(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("stdout", "") or ""
    if isinstance(item, list):
        parts: List[str] = []
        for elem in item:
            if isinstance(elem, dict):
                parts.append(elem.get("stdout", "") or "")
        return "\n".join(parts)
    return ""


def _extract_stderr(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("stderr", "") or ""
    if isinstance(item, list):
        parts: List[str] = []
        for elem in item:
            if isinstance(elem, dict):
                parts.append(elem.get("stderr", "") or "")
        return "\n".join(parts)
    return ""


def _returncode(item: Any) -> int:
    if isinstance(item, dict):
        return int(item.get("returncode", 0) or 0)
    return 0


class SynthesizerAgent:

    _NETWORK_SIGNATURES = (
        "Nmap scan report", "Host is up", "[ether]",
        "MAC Address:", "PORT   STATE", "Nmap done", "Starting Nmap",
    )

    def __init__(self) -> None:
        model = Config.MODELS.get(Config.DEFAULT_MODEL, "qwen2.5:latest")
        self.llm = OllamaClient(model)
        self._tracer = get_tracer()
        self.web_agent = WebResearchAgent()
        try:
            self.system_prompt = build_system_prompt("agents/synthesizer")
        except Exception:
            self.system_prompt = "Summarize execution results clearly for a cybersecurity professional."

    def synthesize(
        self,
        all_results: List[Any],
        objective: str = "",
        phase: str = "general",
        context: dict | None = None,
    ) -> str:
        self._tracer.log("synthesizer", "synthesize_start", {
            "phase": phase,
            "result_count": len(all_results),
        })
        if not all_results:
            language = (context or {}).get("language") or build_language_context(objective)
            return "No hay resultados para sintetizar." if language.get("code") == "es" else "No results to synthesize."

        is_network = (phase == "network_recon") or self._is_network_output(all_results)
        output = (
            self._synthesize_network(all_results, objective, context=context)
            if is_network else
            self._synthesize_generic(all_results, objective, context=context)
        )

        self._tracer.log("synthesizer", "synthesize_done", {"output_len": len(output)})
        return output

    def _synthesize_network(
        self,
        results: List[Any],
        objective: str,
        context: dict | None = None,
    ) -> str:
        report = NetworkReport()
        errors: list[str] = []
        scan_failures: dict[str, str] = {}

        for item in results:
            stdout = _extract_stdout(item)
            if stdout.strip():
                report.ingest(stdout)
            stderr = _extract_stderr(item)
            if _returncode(item) != 0 and stderr.strip():
                errors.append(stderr)
                if isinstance(item, dict) and item.get("target_ip"):
                    scan_failures[str(item["target_ip"])] = stderr

        lookup_enabled = any(
            token in (objective or "").lower()
            for token in ("vulner", "cve", "attack", "ataque", "prioriza", "prioritize")
        )
        research_context = (context or {}).get("research", {})
        enrich_enabled = lookup_enabled or research_context.get("route_mode") == "augment"
        vuln_lookup = self.web_agent.enrich_vulnerability_hypothesis if enrich_enabled else None

        markdown = render_network_markdown(
            hosts=report.hosts(),
            objective=objective,
            errors=errors,
            scan_failures=scan_failures,
            vuln_lookup=vuln_lookup,
            time_context=(context or {}).get("time_context"),
            language_context=(context or {}).get("language"),
        )
        return markdown

    def _synthesize_generic(
        self,
        results: List[Any],
        objective: str,
        context: dict | None = None,
    ) -> str:
        clipped: List[dict] = []
        for item in results[:10]:
            if isinstance(item, dict):
                clipped.append({
                    "command": item.get("command", ""),
                    "returncode": item.get("returncode", "?"),
                    "stdout": (item.get("stdout", "") or "")[:500],
                    "stderr": (item.get("stderr", "") or "")[:300],
                })
            elif isinstance(item, list):
                batch: List[dict] = []
                for elem in item[:5]:
                    if isinstance(elem, dict):
                        batch.append({
                            "command": elem.get("command", ""),
                            "returncode": elem.get("returncode", "?"),
                            "stdout": (elem.get("stdout", "") or "")[:300],
                        })
                clipped.append({"batch_results": batch})

        language_context = (context or {}).get("language") or build_language_context(objective)
        user_prompt = (
            f"{build_runtime_context_block(time_context=(context or {}).get('time_context'), language_context=language_context)}\n\n"
            f"Objective: {objective}\n\n"
            f"Execution Results:\n{json.dumps(clipped, ensure_ascii=False, indent=2)}\n\n"
            "Synthesize into a clear summary for the user while preserving the language policy."
        )
        try:
            return self.llm.chat(self.system_prompt, user_prompt)
        except Exception as exc:
            logger.error(f"[Synthesizer] LLM failed: {exc}")
            parts = [_extract_stdout(item) for item in results if _extract_stdout(item)]
            return "\n\n".join(parts) if parts else "No output captured."

    def _is_network_output(self, results: List[Any]) -> bool:
        for item in results:
            stdout = _extract_stdout(item)
            if any(signature in stdout for signature in self._NETWORK_SIGNATURES):
                return True
        return False
