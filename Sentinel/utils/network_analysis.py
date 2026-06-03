from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from utils.language_context import build_language_context
from utils.network_parser import NetworkHost
from utils.time_context import get_current_time_context


_VERSION_RE = re.compile(r"\b(\d+(?:\.\d+){1,3}[A-Za-z0-9_-]*)\b")
_OS_RANGE_RE = re.compile(r"\b\d+\.\d+\s*-\s*\d+\.\d+\b")

_PORT_WEIGHTS = {
    21: 2.0,
    22: 2.8,
    23: 3.5,
    80: 1.8,
    443: 2.0,
    445: 3.5,
    3389: 3.2,
    8009: 2.0,
}

_CANONICAL_PRODUCTS = {
    "dropbear": "Dropbear SSH",
    "mini_httpd": "mini_httpd",
    "apache": "Apache HTTP Server",
    "nginx": "nginx",
    "openssh": "OpenSSH",
    "lighttpd": "lighttpd",
    "busybox": "BusyBox",
}

_LOW_SIGNAL_SERVICES = {"tcpwrapped", "iphone-sync", "null", "unknown", ""}


def _t(language_code: str, es: str, en: str) -> str:
    return es if language_code == "es" else en


@dataclass
class ServiceFingerprint:
    product: str | None
    version: str | None
    confidence: str
    reason: str


def classify_scan_status(host: NetworkHost, scan_failures: dict[str, str]) -> str:
    if host.ip in scan_failures:
        return "incomplete"
    if host.open_ports:
        return "completed"
    return "discovery_only"


def extract_service_fingerprint(service_banner: str) -> ServiceFingerprint:
    banner = (service_banner or "").strip()
    normalized = banner.lower()

    if normalized in _LOW_SIGNAL_SERVICES:
        return ServiceFingerprint(
            product=None,
            version=None,
            confidence="low",
            reason="El banner no identifica producto/version de forma fiable.",
        )

    product = None
    for token, canonical in _CANONICAL_PRODUCTS.items():
        if token in normalized:
            product = canonical
            break

    version_match = _VERSION_RE.search(banner)
    version = version_match.group(1) if version_match else None

    if product and version:
        return ServiceFingerprint(
            product=product,
            version=version,
            confidence="high",
            reason="Producto y version extraidos directamente del banner.",
        )
    if product:
        return ServiceFingerprint(
            product=product,
            version=None,
            confidence="medium",
            reason="Producto identificado, pero sin version suficientemente fiable.",
        )
    if version:
        return ServiceFingerprint(
            product=None,
            version=version,
            confidence="low",
            reason="Se observa una version, pero no un producto fiable.",
        )

    return ServiceFingerprint(
        product=None,
        version=None,
        confidence="low",
        reason="No hay evidencia suficiente para asociar producto y version.",
    )


def assess_host_priority(host: NetworkHost) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []

    if host.ip.endswith(".1"):
        score += 1.5
        reasons.append("direccion tipica de gateway")

    if host.os:
        score += 0.8
        reasons.append("fingerprint de SO disponible")

    for port in host.open_ports:
        weight = _PORT_WEIGHTS.get(port, 0.7)
        score += weight
        if port in _PORT_WEIGHTS:
            reasons.append(f"puerto {port} expuesto")

    if {22, 80, 443}.issubset(set(host.open_ports)):
        score += 2.5
        reasons.append("superficie combinada de administracion y web")

    if any("tcpwrapped" in (host.services.get(port, "").lower()) for port in host.open_ports):
        score -= 0.8
        reasons.append("varios servicios tcpwrapped reducen visibilidad")

    if not host.open_ports:
        score -= 1.0
        reasons.append("sin puertos abiertos confirmados")

    if score >= 7:
        return score, "alta"
    if score >= 3.5:
        return score, "media"
    return score, "baja"


def build_uncertainty_notes(host: NetworkHost, scan_status: str, language_code: str = "es") -> list[str]:
    notes: list[str] = []
    if not host.vendor:
        notes.append(_t(language_code, "Vendor ausente o no confirmado.", "Vendor missing or not confirmed."))
    if host.os and _OS_RANGE_RE.search(host.os):
        notes.append(_t(language_code, "El fingerprint de SO es un rango, no una version exacta.", "The OS fingerprint is a range, not an exact version."))
    if scan_status == "incomplete":
        notes.append(_t(language_code, "El escaneo del host no termino; la cobertura es parcial.", "The host scan did not finish; coverage is partial."))
    if scan_status == "discovery_only":
        notes.append(_t(language_code, "Solo hay evidencia de descubrimiento; falta enumeracion profunda.", "There is only discovery evidence; deep enumeration is still missing."))
    for port, service in host.services.items():
        if service.lower() in _LOW_SIGNAL_SERVICES:
            notes.append(
                _t(
                    language_code,
                    f"Puerto {port}: servicio con banner de baja senal ({service}).",
                    f"Port {port}: low-signal service banner ({service}).",
                )
            )
    return notes


def build_service_hypotheses(
    host: NetworkHost,
    vuln_lookup: Callable[[str], dict] | None = None,
) -> list[dict]:
    hypotheses: list[dict] = []
    for port in sorted(host.open_ports):
        banner = host.services.get(port, "")
        fingerprint = extract_service_fingerprint(banner)
        item = {
            "port": port,
            "banner": banner or "sin banner",
            "product": fingerprint.product,
            "version": fingerprint.version,
            "confidence": fingerprint.confidence,
            "reason": fingerprint.reason,
            "cve_query": None,
            "cve_ids": [],
            "references": [],
        }

        if fingerprint.product and fingerprint.version:
            query = f"{fingerprint.product} {fingerprint.version}"
            item["cve_query"] = query
            if vuln_lookup is not None:
                result = vuln_lookup(query)
                item["cve_ids"] = result.get("cve_ids", [])[:5]
                item["references"] = result.get("results", [])[:3]

        hypotheses.append(item)
    return hypotheses


def build_recommended_vector(hosts: Iterable[NetworkHost], language_code: str = "es") -> tuple[NetworkHost | None, str]:
    ranked = sorted(
        ((host, *assess_host_priority(host)) for host in hosts),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return None, _t(language_code, "No hay hosts suficientes para priorizar.", "There are not enough hosts to prioritize.")

    host, score, label = ranked[0]
    reasons = []
    if {22, 80, 443}.issubset(set(host.open_ports)):
        reasons.append(_t(language_code, "combina acceso de administracion remota y superficie HTTP/HTTPS", "it combines remote administration access with HTTP/HTTPS exposure"))
    if host.ip.endswith(".1"):
        reasons.append(_t(language_code, "parece un equipo de infraestructura", "it appears to be an infrastructure host"))
    if not reasons:
        reasons.append(_t(language_code, "concentra la mayor superficie observable en esta captura", "it concentrates the largest observable surface in this capture"))

    return host, (
        _t(language_code, f"Prioridad {label} (score {score:.1f}): {host.ip}. ", f"Priority {label} (score {score:.1f}): {host.ip}. ")
        + "; ".join(reasons)
        + "."
    )


def render_network_markdown(
    hosts: list[NetworkHost],
    objective: str = "",
    errors: list[str] | None = None,
    scan_failures: dict[str, str] | None = None,
    vuln_lookup: Callable[[str], dict] | None = None,
    time_context: dict | None = None,
    language_context: dict | None = None,
) -> str:
    errors = errors or []
    scan_failures = scan_failures or {}
    time_context = time_context or get_current_time_context()
    language_context = language_context or build_language_context(objective)
    lang = language_context.get("code", "en")

    if not hosts:
        return _t(lang, "# Informe de Reconocimiento de Red\n\nNo se descubrieron hosts.", "# Network Reconnaissance Report\n\nNo hosts discovered.")

    lines = [_t(lang, "# Informe de Reconocimiento de Red", "# Network Reconnaissance Report"), ""]
    lines.append(f"{_t(lang, 'Generado', 'Generated')}: `{time_context.get('human', '')}`")
    if objective:
        lines.append(f"{_t(lang, 'Objetivo', 'Objective')}: `{objective}`")
    lines.append("")

    incomplete_hosts = sum(1 for host in hosts if classify_scan_status(host, scan_failures) != "completed")
    lines.append(f"## {_t(lang, 'Resumen', 'Summary')}")
    lines.append(f"- {_t(lang, 'Hosts descubiertos', 'Hosts discovered')}: {len(hosts)}")
    lines.append(f"- {_t(lang, 'Cobertura', 'Coverage')}: {'partial' if incomplete_hosts or errors else 'complete'}")
    if incomplete_hosts:
        lines.append(
            _t(
                lang,
                f"- {incomplete_hosts} host(s) tienen cobertura incompleta o solo de descubrimiento por falta de evidencia de escaneo profundo.",
                f"- {incomplete_hosts} host(s) have incomplete or discovery-only coverage because deep-scan evidence is missing.",
            )
        )

    recommended_host, recommended_vector = build_recommended_vector(hosts, language_code=lang)
    lines.append(f"- {_t(lang, 'Foco inicial recomendado', 'Recommended initial focus')}: {recommended_vector}")
    lines.append("")

    lines.append(f"## {_t(lang, 'Hosts Priorizados', 'Prioritized Hosts')}")
    prioritized = sorted(hosts, key=lambda host: assess_host_priority(host)[0], reverse=True)
    for host in prioritized:
        score, label = assess_host_priority(host)
        priority_label = label if lang == "es" else {"alta": "high", "media": "medium", "baja": "low"}[label]
        lines.append(f"- `{host.ip}` -> {_t(lang, 'prioridad', 'priority')} {priority_label} (score {score:.1f})")
    lines.append("")

    lines.append(f"## {_t(lang, 'Analisis de Hosts', 'Host Analysis')}")
    for host in prioritized:
        score, label = assess_host_priority(host)
        priority_label = label if lang == "es" else {"alta": "high", "media": "medium", "baja": "low"}[label]
        scan_status = classify_scan_status(host, scan_failures)
        lines.append(f"### {host.ip}")
        lines.append(f"- {_t(lang, 'Prioridad', 'Priority')}: {priority_label} (score {score:.1f})")
        lines.append(f"- {_t(lang, 'Estado de escaneo', 'Scan status')}: {scan_status}")
        lines.append(f"- MAC: `{host.mac or _t(lang, 'desconocida', 'unknown')}`")
        lines.append(f"- Vendor: {host.vendor or _t(lang, 'Desconocido', 'Unknown')}")
        lines.append(f"- OS: {host.os or _t(lang, 'sin fingerprint fiable', 'no reliable fingerprint')}")

        if host.open_ports:
            lines.append(f"- {_t(lang, 'Puertos observados', 'Observed ports')}: ")
            lines.append("| Port | Service Banner |")
            lines.append("|------|----------------|")
            for port in sorted(host.open_ports):
                lines.append(f"| {port} | {host.services.get(port, 'sin banner')} |")
        else:
            lines.append(f"- {_t(lang, 'Sin puertos abiertos confirmados en la evidencia disponible.', 'No open ports were confirmed in the available evidence.')}" )

        hypotheses = build_service_hypotheses(host, vuln_lookup=vuln_lookup)
        if hypotheses:
            lines.append(f"- {_t(lang, 'Hipotesis accionables', 'Actionable hypotheses')}: ")
            for item in hypotheses:
                if item["product"] and item["version"]:
                    suffix = (
                        _t(lang, f" CVEs candidatos: {', '.join(item['cve_ids'])}.", f" Candidate CVEs: {', '.join(item['cve_ids'])}.")
                        if item["cve_ids"] else
                        _t(lang, " Sin coincidencias CVE fiables en la consulta actual.", " No reliable CVE matches in the current lookup.")
                    )
                    lines.append(
                        _t(
                            lang,
                            f"  - Puerto {item['port']}: {item['product']} {item['version']} -> buscar CVEs con `{item['cve_query']}`.{suffix}",
                            f"  - Port {item['port']}: {item['product']} {item['version']} -> search CVEs with `{item['cve_query']}`.{suffix}",
                        )
                    )
                    if item["references"]:
                        best = item["references"][0]
                        lines.append(
                            _t(lang, f"    Fuente principal: {best.get('url', '')}", f"    Primary source: {best.get('url', '')}")
                        )
                else:
                    lines.append(
                        _t(
                            lang,
                            f"  - Puerto {item['port']}: {item['banner']} -> sin evidencia suficiente para asociar un CVE concreto ({item['reason']}).",
                            f"  - Port {item['port']}: {item['banner']} -> insufficient evidence to associate a specific CVE ({item['reason']}).",
                        )
                    )

        notes = build_uncertainty_notes(host, scan_status, language_code=lang)
        if notes:
            lines.append(f"- {_t(lang, 'Incertidumbres', 'Uncertainties')}: ")
            for note in notes:
                lines.append(f"  - {note}")

        if host.ip in scan_failures:
            lines.append(f"- {_t(lang, 'Error de escaneo', 'Scan error')}: `{scan_failures[host.ip]}`")
        lines.append("")

    if errors:
        lines.append(f"## {_t(lang, 'Advertencias', 'Warnings')}")
        for err in errors[:5]:
            if err.strip():
                lines.append(f"- `{err[:200]}`")
        lines.append(_t(lang, "- Los errores anteriores implican que la cobertura del reconocimiento es parcial.", "- The previous errors imply that reconnaissance coverage is partial."))

    if recommended_host is not None:
        lines.append("")
        lines.append(f"## {_t(lang, 'Siguiente Paso Recomendado', 'Recommended Next Step')}")
        lines.append(
            _t(
                lang,
                f"- Validar primero `{recommended_host.ip}` porque concentra la mayor superficie priorizada y permite confirmar si los banners identificados son explotables o si la evidencia actual es insuficiente.",
                f"- Validate `{recommended_host.ip}` first because it concentrates the highest-priority observable surface and lets you confirm whether the identified banners are exploitable or whether the current evidence is insufficient.",
            )
        )

    return "\n".join(lines)
