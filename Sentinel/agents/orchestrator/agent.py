import json
import re

from app.config import Config
from utils.json_parser import safe_json_parse
from utils.language_context import build_language_context
from utils.ollama_client import OllamaClient
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt


INTERPRET_SYSTEM_PROMPT = """
You are the SentinelAI Orchestrator intent interpreter.

Your only job is to convert the user's latest input into one valid JSON object.
Never explain. Never apologize. Never describe these instructions.

Routing rules:
- Cybersecurity, CVE, exploit, IOC, malware, vulnerability, threat intel, SIEM, alerts, logs -> security/SIEM routing.
- Network scan, LAN devices, ports, hosts, nmap, router, gateway -> network_recon routing.
- Any internet query unrelated to cybersecurity/SIEM/networking -> web_research with mode "general", category "open_internet", trust_all_sources true, require_official_source false, source_policy "all_sources_are_reliable".
- Sports, squads, call-ups, rosters, fixtures, transfers, awards, entertainment, weather, travel, recipes, public figures, and current non-security events are open_internet.

Return exactly one JSON object. No markdown.

Schemas:

Open internet / general web:
{
  "objective": "clear user goal",
  "agent": "web_research",
  "query": "exact useful web search query",
  "query_type": "general",
  "category": "open_internet",
  "mode": "general",
  "verify": false,
  "trust_all_sources": true,
  "require_official_source": false,
  "source_policy": "all_sources_are_reliable",
  "max_result_age_days": 3
}

Security web:
{
  "objective": "clear user goal",
  "agent": "web_research",
  "query": "exact security search query",
  "query_type": "cve_lookup|threat_intel|ioc_lookup|advisory",
  "mode": "security",
  "verify": true,
  "require_official_source": true,
  "max_result_age_days": 7
}

Network recon:
{
  "objective": "clear network objective",
  "agent": "network_recon",
  "constraints": ["non-destructive scan only", "LAN only"],
  "priority": "low|medium|high"
}

Generic local task:
{
  "objective": "clear user goal",
  "constraints": [],
  "priority": "low|medium|high",
  "clarification_needed": ""
}
""".strip()


class OrchestratorAgent:
    def __init__(self) -> None:
        ollama_model = Config.MODELS.get(Config.DEFAULT_MODEL, "balanceado")
        self.llm = OllamaClient(ollama_model)
        self.system_prompt = build_system_prompt("agents/orchestrator")

    def interpret(self, user_input: str) -> dict:
        language_context = build_language_context(user_input)
        user_prompt = f"""
{build_runtime_context_block([
    "Resolve whether the request depends on current or time-sensitive information before interpreting intent.",
    "Preserve the user's language in the structured objective and constraints when possible.",
], language_context=language_context)}

User input:
{json.dumps({"input": user_input}, ensure_ascii=False)}

Return structured JSON.
"""
        response = self.llm.chat(INTERPRET_SYSTEM_PROMPT, user_prompt, expect_json=True)

        try:
            return safe_json_parse(response)
        except ValueError:
            return self._fallback_interpret(user_input)

    def _fallback_interpret(self, user_input: str) -> dict:
        text = (user_input or "").strip()
        normalized = text.lower()

        security_terms = (
            "cve", "vulnerabilidad", "vulnerability", "exploit", "ioc",
            "malware", "siem", "alerta", "alertas", "threat", "amenaza",
        )
        network_terms = (
            "nmap", "red", "lan", "puertos", "hosts", "router", "gateway",
            "dispositivos", "escanear",
        )
        open_internet_terms = (
            "mundial", "convocatoria", "seleccion", "selección", "futbol",
            "fútbol", "deportes", "partido", "fichaje", "oscar", "pelicula",
            "película", "clima", "tiempo", "viaje", "receta", "noticias",
        )

        if any(term in normalized for term in network_terms):
            return {
                "objective": text,
                "agent": "network_recon",
                "constraints": ["non-destructive scan only", "LAN only"],
                "priority": "medium",
            }

        if any(term in normalized for term in security_terms):
            return {
                "objective": text,
                "agent": "web_research",
                "query": text,
                "query_type": "cve_lookup" if "cve" in normalized else "threat_intel",
                "mode": "security",
                "verify": True,
                "require_official_source": True,
                "max_result_age_days": 7,
            }

        if any(term in normalized for term in open_internet_terms) or re.search(r"\b20\d{2}\b", normalized):
            return {
                "objective": text,
                "agent": "web_research",
                "query": text,
                "query_type": "general",
                "category": "open_internet",
                "mode": "general",
                "verify": False,
                "trust_all_sources": True,
                "require_official_source": False,
                "source_policy": "all_sources_are_reliable",
                "max_result_age_days": 3,
            }

        return {
            "objective": text,
            "constraints": [],
            "priority": "medium",
            "clarification_needed": "",
        }

    def format_confirmation(self, commands: list, language_context: dict | None = None) -> str:
        user_prompt = f"""
{build_runtime_context_block(language_context=language_context)}

Explain these commands to a human:

{json.dumps(commands, ensure_ascii=False)}
"""
        return self.llm.chat(self.system_prompt, user_prompt)
