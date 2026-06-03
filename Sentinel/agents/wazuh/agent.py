"""
agents/wazuh/agent.py

WazuhAgent: lee y procesa datos de Wazuh con LLM.
Cubre lectura reactiva (por consulta del usuario) y
resumen proactivo (llamado desde el monitor en background).
"""
from __future__ import annotations

import json
from typing import Any

from app.config import Config
from utils.logger import logger
from utils.ollama_client import OllamaClient
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from utils.wazuh_client import WazuhClient, WazuhAPIError, WazuhAuthError


def _summarize_alert(alert: dict) -> dict:
    """Extrae los campos más relevantes de una alerta cruda."""
    return {
        "id":          alert.get("id", ""),
        "timestamp":   alert.get("timestamp", ""),
        "agent":       alert.get("agent", {}).get("name", "unknown"),
        "agent_ip":    alert.get("agent", {}).get("ip", ""),
        "rule_id":     alert.get("rule", {}).get("id", ""),
        "rule_level":  alert.get("rule", {}).get("level", 0),
        "description": alert.get("rule", {}).get("description", ""),
        "groups":      alert.get("rule", {}).get("groups", []),
        "full_log":    (alert.get("full_log") or "")[:300],
    }


def _agent_line(agent: dict) -> str:
    os_data = agent.get("os", {}) or {}
    return (
        f"- `{agent.get('id', '')}` {agent.get('name', 'sin nombre')} | "
        f"estado: {agent.get('status', 'desconocido')} | "
        f"IP: {agent.get('ip') or agent.get('registerIP') or 'N/A'} | "
        f"SO: {os_data.get('name') or os_data.get('platform') or 'N/A'} | "
        f"version: {agent.get('version', 'N/A')}"
    )


def _alert_line(alert: dict) -> str:
    summary = _summarize_alert(alert)
    return (
        f"- nivel {summary['rule_level']} | regla `{summary['rule_id']}` | "
        f"agente: {summary['agent']} | {summary['timestamp']} | "
        f"{summary['description']}"
    )


class WazuhAgent:

    def __init__(self) -> None:
        self.client = WazuhClient()
        model = Config.MODELS.get(Config.DEFAULT_MODEL, "balanceado")
        self.llm = OllamaClient(model)
        try:
            self.system_prompt = build_system_prompt("agents/wazuh")
        except Exception:
            self.system_prompt = (
                "Eres un analista de seguridad experto. Analiza datos de Wazuh "
                "y proporciona resúmenes claros, priorizados y accionables."
            )

    def is_available(self) -> bool:
        return self.client.is_available()

    # ─────────────────────────────────────────────────────────────
    # Respuesta reactiva (por consulta del usuario)
    # ─────────────────────────────────────────────────────────────

    def respond(self, user_input: str, objective: str = "") -> str:
        """
        Punto de entrada principal cuando el usuario hace una consulta
        relacionada con Wazuh.
        """
        text = f"{user_input} {objective}".lower()

        try:
            if any(kw in text for kw in ("alerta", "alert", "alarma", "siem", "críti", "criti", "level")):
                return self._handle_alerts_query(text)

            if any(kw in text for kw in ("log", "registro")):
                return self._handle_logs_query()

            if any(kw in text for kw in ("regla", "rule", "detección", "deteccion")):
                return self._handle_rules_query(text)

            if any(kw in text for kw in ("agente", "agent", "endpoint", "conectado", "connected", "desconectado")):
                return self._handle_agents_query()

            # Sin keyword específico → resumen general
            return self._handle_general_summary()

        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.error(f"[WazuhAgent] API error: {exc}")
            return f"⚠️ No se pudo conectar con Wazuh: {exc}"

    def _handle_alerts_query(self, text: str) -> str:
        min_level = Config.WAZUH_ALERT_LEVEL_MIN
        # Ajustar nivel según la consulta
        if any(kw in text for kw in ("todo", "all", "baja", "low")):
            min_level = 0
        elif any(kw in text for kw in ("críti", "criti", "alta", "high", "urgent")):
            min_level = 12

        hours = 24
        if any(kw in text for kw in ("semana", "week", "7 dias", "7 días")):
            hours = 24 * 7
        elif any(kw in text for kw in ("hora", "hour", "ultima hora", "última hora")):
            hours = 1

        try:
            alerts = self.client.get_indexer_alerts(limit=100, min_level=min_level, hours=hours)
        except WazuhAPIError:
            alerts = self.client.get_alerts(limit=100, min_level=min_level)
        return self._format_alerts(alerts, min_level=min_level, hours=hours)

    def _handle_logs_query(self) -> str:
        logs = self.client.get_logs(limit=100)
        logs_text = json.dumps(logs[:50], indent=2, ensure_ascii=False)
        return self._llm_analyze(
            data=logs_text,
            task="Resume los logs más recientes. Destaca errores, warnings o patrones sospechosos.",
        )

    def _handle_rules_query(self, text: str) -> str:
        level = None
        if any(kw in text for kw in ("críti", "criti", "alta", "high")):
            level = 10
        rules = self.client.get_rules(limit=200, level=level)
        if not rules:
            return "No he encontrado reglas Wazuh con ese filtro."
        lines = [
            f"Reglas Wazuh encontradas: {len(rules)}"
            + (f" (nivel {level}+)" if level is not None else ""),
            "",
        ]
        for rule in rules[:30]:
            groups = ", ".join(rule.get("groups", [])[:5]) if isinstance(rule.get("groups"), list) else ""
            lines.append(
                f"- regla `{rule.get('id', '')}` | nivel {rule.get('level', 'N/A')} | "
                f"{rule.get('description', 'sin descripcion')} | grupos: {groups or 'N/A'}"
            )
        if len(rules) > 30:
            lines.append(f"\nMostrando 30 de {len(rules)} reglas.")
        return "\n".join(lines)

    def _handle_agents_query(self) -> str:
        agents = self.client.get_agents(status=None)
        if not agents:
            return "No he encontrado agentes registrados en Wazuh."

        real_agents = [a for a in agents if str(a.get("id", "")) != "000"]
        active = [a for a in real_agents if a.get("status") == "active"]
        disconnected = [a for a in real_agents if a.get("status") != "active"]

        lines = [
            "Estado de agentes Wazuh:",
            f"- conectados: {len(active)}",
            f"- no conectados / con problemas: {len(disconnected)}",
            f"- total endpoints: {len(real_agents)}",
            "",
            "Agentes conectados:",
        ]
        lines.extend(_agent_line(agent) for agent in active[:30])
        if disconnected:
            lines.append("")
            lines.append("Agentes no activos:")
            lines.extend(_agent_line(agent) for agent in disconnected[:30])
        return "\n".join(lines)

    def _handle_general_summary(self) -> str:
        alerts  = self.client.get_critical_alerts(limit=30)
        agents  = self.client.get_agents(status=None)
        summary = {
            "total_critical_alerts": len(alerts),
            "top_alerts": [_summarize_alert(a) for a in alerts[:10]],
            "total_agents": len(agents),
            "agents_disconnected": [
                a for a in agents if a.get("status") != "active"
            ],
        }
        return self._llm_analyze(
            data=json.dumps(summary, indent=2, ensure_ascii=False),
            task="Proporciona un resumen ejecutivo del estado de seguridad. Prioriza por urgencia.",
        )

    # ─────────────────────────────────────────────────────────────
    # Resumen proactivo (llamado desde el monitor en background)
    # ─────────────────────────────────────────────────────────────

    def proactive_check(self) -> dict[str, Any]:
        """
        Llamado periódicamente desde el background poller.
        Devuelve dict con: has_critical, count, summary, alerts.
        """
        try:
            alerts = self.client.get_critical_alerts(limit=20)
            if not alerts:
                return {"has_critical": False, "count": 0, "summary": "", "alerts": []}

            summarized = [_summarize_alert(a) for a in alerts]
            summary = self._llm_analyze(
                data=json.dumps(summarized, indent=2, ensure_ascii=False),
                task=(
                    "Resumen proactivo de alertas críticas. Sé muy conciso (máx 3 frases). "
                    "Indica el agente afectado, tipo de amenaza y acción recomendada."
                ),
                max_tokens=300,
            )
            return {
                "has_critical": True,
                "count": len(alerts),
                "summary": summary,
                "alerts": summarized,
            }
        except Exception as exc:
            logger.error(f"[WazuhAgent] proactive_check error: {exc}")
            return {"has_critical": False, "count": 0, "summary": str(exc), "alerts": []}

    # ─────────────────────────────────────────────────────────────
    # LLM helpers
    # ─────────────────────────────────────────────────────────────

    def _synthesize_alerts(self, alerts: list[dict], context_label: str) -> str:
        if not alerts:
            return f"No se encontraron alertas ({context_label})."
        summarized = [_summarize_alert(a) for a in alerts]
        return self._llm_analyze(
            data=json.dumps(summarized, indent=2, ensure_ascii=False),
            task=(
                f"Analiza estas alertas Wazuh ({context_label}). "
                "Agrupa por tipo/agente, prioriza por nivel de riesgo, "
                "e identifica patrones o posibles ataques en curso."
            ),
        )

    def _llm_analyze(self, data: str, task: str, max_tokens: int = 1500) -> str:
        user_prompt = (
            f"{build_runtime_context_block()}\n\n"
            f"Tarea: {task}\n\n"
            f"Datos Wazuh:\n```json\n{data[:4000]}\n```"
        )
        try:
            return self.llm.chat(self.system_prompt, user_prompt)
        except Exception as exc:
            logger.error(f"[WazuhAgent] LLM analysis failed: {exc}")
            return f"Datos obtenidos de Wazuh (análisis LLM no disponible):\n{data[:2000]}"

    def _format_alerts(self, alerts: list[dict], min_level: int, hours: int) -> str:
        if not alerts:
            return f"No se encontraron alertas Wazuh de nivel >= {min_level} en las ultimas {hours}h."

        critical = [a for a in alerts if int((a.get("rule") or {}).get("level", 0) or 0) >= 10]
        agents = sorted({
            (a.get("agent") or {}).get("name", "unknown")
            for a in alerts
        })
        lines = [
            f"Alertas Wazuh en las ultimas {hours}h:",
            f"- total mostradas: {len(alerts)}",
            f"- criticas/altas (nivel >= 10): {len(critical)}",
            f"- agentes afectados: {', '.join(agents[:12]) or 'N/A'}",
            "",
            "Ultimas alertas:",
        ]
        lines.extend(_alert_line(alert) for alert in alerts[:20])
        if len(alerts) > 20:
            lines.append(f"\nMostrando 20 de {len(alerts)} alertas.")
        return "\n".join(lines)
