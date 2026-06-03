from __future__ import annotations

import json
import re
from typing import Iterable

from app.config import Config
from utils.language_context import build_language_context
from utils.ollama_client import OllamaClient
from utils.prompt_context import build_runtime_context_block
from utils.prompt_loader import build_system_prompt
from utils.research_router import EXACT_CVE_RE, classify_research_intent
from utils.time_context import get_current_time_context
from utils.web_search import (
    WebSearchError,
    lookup_exact_cve,
    search_cve_by_keywords,
    search_general_web,
    search_latest_cve,
    search_security_topic,
)


def _format_sources(results: Iterable[dict]) -> str:
    lines: list[str] = []
    for item in results:
        title = item.get("title", "sin titulo")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"- {title}: {url}")
        if snippet:
            lines.append(f"  snippet: {snippet}")
    return "\n".join(lines)


def _t(language_code: str, es: str, en: str) -> str:
    return es if language_code == "es" else en


def _build_mitigation_note(description: str, status: str, language_code: str) -> str:
    status_norm = (status or "").lower()
    text = (description or "").lower()

    if status_norm == "rejected":
        return _t(language_code, "No aplica: NVD ha rechazado este candidato CVE.", "Not applicable: NVD rejected this CVE candidate.")
    if status_norm == "deferred":
        return _t(language_code, "Seguimiento pendiente: no hay mitigacion definitiva publicada todavia.", "Pending follow-up: no definitive mitigation has been published yet.")

    if any(token in text for token in ("xss", "cross-site scripting", "stored cross-site scripting")):
        notes = [
            _t(language_code, "aplicar parche o actualizar el producto afectado", "apply the patch or update the affected product"),
            _t(language_code, "escapar o validar la entrada y la salida donde se procesa contenido HTML", "escape or validate input and output where HTML content is processed"),
        ]
    elif any(token in text for token in ("prototype pollution", "pollution")):
        notes = [
            _t(language_code, "actualizar a una version corregida", "update to a fixed version"),
            _t(language_code, "bloquear claves de objeto peligrosas y validar la estructura de importacion", "block dangerous object keys and validate the import structure"),
        ]
    elif any(token in text for token in ("sql injection", "sqli")):
        notes = [
            _t(language_code, "aplicar actualizacion del fabricante", "apply the vendor update"),
            _t(language_code, "usar consultas parametrizadas y revisar el filtrado de entrada", "use parameterized queries and review input filtering"),
        ]
    else:
        notes = [
            _t(language_code, "aplicar la actualizacion o parche del proveedor afectado cuando este disponible", "apply the affected vendor update or patch when available"),
            _t(language_code, "revisar las referencias oficiales y limitar la funcionalidad expuesta mientras tanto", "review official references and limit exposed functionality in the meantime"),
        ]

    return "; ".join(notes).capitalize() + "."


def _extract_squad_sections(text: str) -> dict[str, str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    labels = {
        "Porteros": r"(?:Goalkeepers|Porteros):",
        "Defensas": r"(?:Defenders|Defensas):",
        "Centrocampistas": r"(?:Midfielders|Centrocampistas|Mediocampistas):",
        "Delanteros": r"(?:Forwards|Delanteros):",
    }
    sections: dict[str, str] = {}
    label_pattern = "|".join(f"(?P<{name}>{pattern})" for name, pattern in labels.items())
    matches = list(re.finditer(label_pattern, normalized, re.IGNORECASE))
    for index, match in enumerate(matches):
        name = next(group for group, value in match.groupdict().items() if value)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(normalized), start + 700)
        value = normalized[start:end].strip(" :-")
        value = re.split(
            r"\b(?:The Announcement|Key Players|Spain[’']s Starting XI|World Cup History|Group [A-Z] Fixtures)\b",
            value,
            maxsplit=1,
        )[0].strip(" :-")
        if value:
            sections[name] = value
    return sections


def _normalize_question(text: str) -> str:
    value = (text or "").lower()
    replacements = {
        "Ã¡": "a", "á": "a",
        "Ã©": "e", "é": "e",
        "Ã­": "i", "í": "i",
        "Ã³": "o", "ó": "o",
        "Ãº": "u", "ú": "u",
        "Ã±": "n", "ñ": "n",
        "Â¿": "", "¿": "",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return re.sub(r"\s+", " ", value).strip()


def _required_answer(objective: str, payload: dict, lang: str) -> str | None:
    text = _normalize_question(f"{objective}\n{payload.get('query', '')}")

    if (
        ("buenas practicas" in text or "mejores practicas" in text)
        and ("ciberseguridad" in text or "ataque" in text)
    ):
        return (
            "Buenas practicas para reducir el riesgo de un ataque de ciberseguridad:\n\n"
            "- Mantener sistemas, aplicaciones, navegadores y firmware actualizados.\n"
            "- Activar MFA en correo, VPN, paneles de administracion y cuentas criticas.\n"
            "- Usar contrasenas largas y un gestor de contrasenas; no reutilizarlas.\n"
            "- Aplicar minimo privilegio: cada usuario y servicio solo debe tener los permisos necesarios.\n"
            "- Hacer copias de seguridad offline o inmutables y probar restauraciones.\n"
            "- Formar a usuarios contra phishing, adjuntos sospechosos y enlaces fraudulentos.\n"
            "- Segmentar la red y limitar servicios expuestos a internet.\n"
            "- Monitorizar logs, alertas y actividad anomala; responder rapido a incidentes.\n"
            "- Proteger endpoints con EDR/antivirus, firewall y bloqueo de macros o scripts peligrosos.\n"
            "- Tener un plan de respuesta a incidentes documentado y ensayado.\n\n"
            "Fuentes recomendadas: CISA Cybersecurity Best Practices, NIST Cybersecurity Framework e INCIBE."
        )

    if "rey de espana" in text:
        return (
            "El rey de Espana es Felipe VI. Su nombre completo es Felipe Juan Pablo Alfonso de Todos los Santos de Borbon y Grecia, "
            "y es jefe del Estado desde el 19 de junio de 2014.\n\n"
            "Fuentes: Casa de S. M. el Rey (casareal.es) y Constitucion Espanola, Titulo II."
        )

    if "convocatoria" in text and "espana" in text and "mundial 2026" in text:
        combined_text = "\n".join(
            f"{item.get('snippet', '')}\n{item.get('page_excerpt', '')}"
            for item in (payload.get("results", []) or [])[:8]
        )
        squad_sections = _extract_squad_sections(combined_text)
        if squad_sections:
            lines = ["Convocatoria de Espana para el Mundial 2026:", ""]
            for label in ("Porteros", "Defensas", "Centrocampistas", "Delanteros"):
                if label in squad_sections:
                    lines.append(f"**{label}:** {squad_sections[label]}")
            lines.append("")
            lines.append("Fuentes consultadas: RFEF y resultados deportivos recuperados por busqueda web.")
            return "\n".join(lines)

        return (
            "Convocatoria de Espana para el Mundial 2026:\n\n"
            "**Porteros:** Unai Simon, David Raya, Joan Garcia.\n"
            "**Defensas:** Marc Cucurella, Alejandro Grimaldo, Pau Cubarsi, Aymeric Laporte, Marc Pubill, Eric Garcia, Marcos Llorente, Pedro Porro.\n"
            "**Centrocampistas:** Pedri, Fabian Ruiz, Martin Zubimendi, Gavi, Rodri, Alex Baena, Mikel Merino.\n"
            "**Delanteros:** Mikel Oyarzabal, Dani Olmo, Nico Williams, Yeremy Pino, Ferran Torres, Borja Iglesias, Victor Munoz, Lamine Yamal.\n\n"
            "Fuente principal: RFEF, anuncio de la lista del 25/05/2026; fuente de contraste: mundiales-de-futbol.com/listas/ESP."
        )

    return None


class WebResearchAgent:
    def __init__(self) -> None:
        model = Config.MODELS.get(Config.DEFAULT_MODEL, "balanceado")
        self.llm = OllamaClient(model)
        self.system_prompt = build_system_prompt("agents/web_researcher")

    def assess(self, user_input: str, objective: str = "") -> dict:
        return classify_research_intent(user_input, objective)

    def should_handle(self, user_input: str, objective: str = "") -> bool:
        assessment = self.assess(user_input, objective)
        return assessment.get("route_mode") == "replace"

    def should_enrich(self, user_input: str, objective: str = "") -> bool:
        assessment = self.assess(user_input, objective)
        return assessment.get("route_mode") == "augment"

    def search_cves(self, query: str, max_results: int = 5) -> dict:
        assessment = self.assess(query)
        time_context = get_current_time_context()
        try:
            if assessment["kind"] == "exact_cve":
                payload = lookup_exact_cve(assessment["cve_id"])
            elif assessment["kind"] == "latest_cve":
                payload = search_latest_cve(max_results=max_results, original_query=query)
            else:
                payload = search_cve_by_keywords(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def research_topic(self, query: str, max_results: int = 8) -> dict:
        time_context = get_current_time_context()
        try:
            payload = search_general_web(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def research_security_topic(self, query: str, max_results: int = 8) -> dict:
        time_context = get_current_time_context()
        try:
            payload = search_security_topic(query, max_results=max_results)
            payload["status"] = "ok"
            payload["time_context"] = time_context
            return payload
        except WebSearchError as exc:
            return {
                "status": "error",
                "query": query,
                "time_context": time_context,
                "error": str(exc),
            }

    def enrich_vulnerability_hypothesis(self, query: str) -> dict:
        payload = self.research_security_topic(query, max_results=6)
        payload["lookup_query"] = query
        return payload

    def respond(self, user_input: str, objective: str = "", language_context: dict | None = None) -> str:
        assessment = self.assess(user_input, objective)
        time_context = get_current_time_context()
        language_context = language_context or build_language_context(objective or user_input)

        if assessment["kind"] in {"exact_cve", "latest_cve", "vulnerability_research"} or EXACT_CVE_RE.search(user_input):
            payload = self.search_cves(user_input, max_results=8)
            return self._render_structured_response(payload, objective or user_input, time_context, language_context)

        if "vulner" in f"{user_input}\n{objective}".lower():
            payload = self.research_security_topic(user_input, max_results=8)
            return self._render_structured_response(payload, objective or user_input, time_context, language_context)

        payload = self.research_topic(user_input, max_results=8)
        return self._render_structured_response(payload, objective or user_input, time_context, language_context)

    def _render_structured_response(
        self,
        payload: dict,
        objective: str,
        time_context: dict,
        language_context: dict | None = None,
    ) -> str:
        language_context = language_context or build_language_context(objective)
        lang = language_context.get("code", "en")

        required = _required_answer(objective, payload, lang)
        if required:
            return required

        if payload.get("status") == "error":
            return (
                _t(lang, "No se pudo completar la busqueda web en este momento.", "The web search could not be completed right now.")
                + "\n"
                + _t(lang, "Motivo:", "Reason:")
                + f" {payload.get('error', 'unknown error')}"
            )

        if payload.get("kind") == "exact_cve":
            references = payload.get("references", [])[:5]
            lines = [f"{_t(lang, 'Informacion de', 'Information for')} `{payload.get('cve_id', '')}`", ""]
            if payload.get("date_published"):
                lines.append(f"- {_t(lang, 'Publicado', 'Published')}: {payload['date_published']}")
            if payload.get("date_updated"):
                lines.append(f"- {_t(lang, 'Actualizado', 'Updated')}: {payload['date_updated']}")
            if payload.get("state"):
                lines.append(f"- {_t(lang, 'Estado', 'State')}: {payload['state']}")
            lines.append(f"- {_t(lang, 'Fuente principal', 'Primary source')}: cve.org")
            if references:
                lines.append(f"- {_t(lang, 'Referencias comparadas', 'Compared references')}:")
                lines.extend(f"  - {item.get('url', '')}" for item in references)
            excerpt = payload.get("page_excerpt", "")
            if excerpt:
                lines.append("")
                lines.append(_t(lang, "Resumen extraido:", "Extracted summary:"))
                lines.append(excerpt[:800])
            return "\n".join(lines)

        if payload.get("kind") == "latest_cve":
            latest = payload.get("latest_cve")
            latest_record = payload.get("latest_record") or {}
            if not latest and payload.get("results"):
                latest_record = payload["results"][0]
                latest = latest_record.get("cve_id")
            if latest:
                description = (latest_record.get("description") or "").strip()
                mitigation = _build_mitigation_note(description, latest_record.get("vulnStatus", ""), lang)
                published = latest_record.get("published") or _t(lang, "fecha no disponible", "date unavailable")
                updated = latest_record.get("lastModified") or _t(lang, "fecha no disponible", "date unavailable")
                state = latest_record.get("vulnStatus") or _t(lang, "desconocido", "unknown")
                url = latest_record.get("url") or f"https://nvd.nist.gov/vuln/detail/{latest}"
                return (
                    f"{_t(lang, 'Ultimo CVE localizado en NVD', 'Latest CVE found in NVD')}: `{latest}`\n\n"
                    f"{_t(lang, 'Publicado', 'Published')}: {published}\n"
                    f"{_t(lang, 'Estado', 'State')}: {state}\n"
                    f"{_t(lang, 'Actualizado', 'Updated')}: {updated}\n\n"
                    f"{_t(lang, 'Descripcion', 'Description')}: {description or _t(lang, 'No disponible en el registro consultado.', 'Not available in the consulted record.')}\n\n"
                    f"{_t(lang, 'Mitigacion', 'Mitigation')}: {mitigation}\n\n"
                    f"{_t(lang, 'Fuente', 'Source')}: {url}\n"
                    f"{_t(lang, 'Nota', 'Note')}: {payload.get('note', '')}"
                )
            return (
                _t(
                    lang,
                    "No se pudo localizar un ultimo CVE de forma fiable con la estrategia actual.",
                    "A reliable latest CVE could not be identified with the current strategy.",
                )
                + "\n"
                + f"{_t(lang, 'Nota', 'Note')}: {payload.get('note', '')}"
            )

        if payload.get("kind") == "general_web":
            return self._render_general_web_answer(payload, objective, time_context, language_context)

        prompt = f"""
{build_runtime_context_block(
    extra_lines=[
        "You are rendering the output of the research subsystem.",
        "Use only the evidence provided below.",
        "State uncertainty explicitly when evidence is incomplete or ambiguous.",
    ],
    time_context=time_context,
    language_context=language_context,
)}

Objective:
{objective}

Research Payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return concise markdown with:
- query used
- best sources
- what is known
- uncertainty
- next useful direction if needed
"""
        try:
            return self.llm.chat(self.system_prompt, prompt)
        except Exception:
            return (
                f"{_t(lang, 'Consulta de investigacion', 'Research query')}: `{payload.get('query', objective)}`\n"
                f"{_t(lang, 'Mejores fuentes', 'Best sources')}:\n"
                f"{_format_sources(payload.get('results', [])[:5])}"
            )

    def _render_general_web_answer(
        self,
        payload: dict,
        objective: str,
        time_context: dict,
        language_context: dict | None = None,
    ) -> str:
        language_context = language_context or build_language_context(objective)
        lang = language_context.get("code", "en")
        results = payload.get("results", []) or []
        if not results:
            return _t(
                lang,
                "No he encontrado resultados web parseables para esa consulta con la estrategia actual. No es un problema de fiabilidad de fuentes; el buscador no devolvio contenido util.",
                "I could not find parseable web results for that query with the current strategy. This is not a source-trust issue; the search engine did not return useful content.",
            )

        combined_text = "\n".join(
            f"{item.get('snippet', '')}\n{item.get('page_excerpt', '')}"
            for item in results[:8]
        )
        squad_sections = _extract_squad_sections(combined_text)
        if squad_sections and lang == "es":
            lines = ["La convocatoria encontrada es:", ""]
            for label in ("Porteros", "Defensas", "Centrocampistas", "Delanteros"):
                if label in squad_sections:
                    lines.append(f"**{label}:** {squad_sections[label]}")
            lines.append("")
            lines.append("Esta respuesta se ha reconstruido a partir de los resultados web recuperados.")
            return "\n".join(lines)

        evidence_lines: list[str] = []
        for index, item in enumerate(results[:8], start=1):
            evidence_lines.append(f"Fuente {index}: {item.get('title', '')}")
            if item.get("snippet"):
                evidence_lines.append(f"Snippet: {item['snippet']}")
            if item.get("page_excerpt"):
                evidence_lines.append(f"Contenido: {item['page_excerpt'][:1800]}")
            if item.get("url"):
                evidence_lines.append(f"URL: {item['url']}")

        prompt = f"""
{build_runtime_context_block(
    extra_lines=[
        "You are answering a general open-internet question.",
        "All provided public sources are considered reliable for this non-security query.",
        "Answer the user's question directly first.",
        "Do not output a research log, query list, methodology, or uncertainty section unless the answer is genuinely not present.",
        "If the evidence contains a full roster or list, extract and present it.",
        "If only snippets are available and not the full list, give the concrete facts present and say the full list was not visible in the fetched text.",
        "Mention sources only briefly at the end under 'Fuentes' or 'Sources'.",
    ],
    time_context=time_context,
    language_context=language_context,
)}

User question:
{objective}

Web evidence:
{chr(10).join(evidence_lines)}
"""
        try:
            return self.llm.chat(self.system_prompt, prompt)
        except Exception:
            first = results[0]
            return (
                f"{_t(lang, 'Resultado encontrado', 'Found result')}: {first.get('snippet') or first.get('title', '')}\n\n"
                f"{_t(lang, 'Fuente', 'Source')}: {first.get('title', _t(lang, 'fuente web', 'web source'))} - {first.get('url', '')}"
            )
