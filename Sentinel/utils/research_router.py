from __future__ import annotations

import ipaddress
import re


EXACT_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b")

_LATEST_PATTERNS = (
    r"\b(last|latest|most recent|newest)\b",
    r"\bultim[oa](?:s)?\b",
    r"\búltim[oa](?:s)?\b",
    r"\breciente(?:s)?\b",
)

_VULN_PATTERNS = (
    r"\bcve(?:s)?\b",
    r"\bvulnerabilit(?:y|ies)\b",
    r"\bvulnerabilidad(?:es)?\b",
    r"\bexploit(?:s)?\b",
    r"\b0day\b",
    r"\b0-day\b",
    r"\badvisories?\b",
    r"\bkev\b",
)

_NETWORK_ASSET_PATTERNS = (
    r"\bhost(?:s)?\b",
    r"\bdevice(?:s)?\b",
    r"\bdispositivo(?:s)?\b",
    r"\brouter\b",
    r"\bgateway\b",
    r"\bservic(?:e|es)\b",
    r"\bservicio(?:s)?\b",
    r"\bpuerto(?:s)?\b",
    r"\bport(?:s)?\b",
    r"\bso\b",
    r"\bos\b",
    r"\bfirmware\b",
)

_COMPARE_PATTERNS = (
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bcomparar\b",
    r"\bfiltra(?:r)?\b",
    r"\bfilter\b",
    r"\bprioriza(?:r)?\b",
)

_GENERAL_WEB_PATTERNS = (
    r"\bbusca(?:r)?\b",
    r"\binternet\b",
    r"\bweb\b",
    r"\bonline\b",
    r"\bactualidad\b",
    r"\bnews\b",
    r"\bnoticias?\b",
    r"\bquien\s+es\b",
    r"\bqui[eÃ©]n\s+es\b",
    r"\bcual(?:es)?\s+es\b",
    r"\bcu[aÃ¡]l(?:es)?\s+es\b",
    r"\bconvocatoria\b",
    r"\bmundial\s+2026\b",
    r"\bbuenas?\s+pr[aÃ¡]cticas?\b",
)
_WAZUH_PATTERNS = (
    r"\bwazuh\b",
    r"\bsiem\b",
    r"\balerta(?:s)?\b",
    r"\balert(?:s)?\b",
    r"\balarma(?:s)?\b",
    r"\bincidente(?:s)?\b",
    r"\bincident(?:s)?\b",
    r"\blog(?:s)?\s+wazuh\b",
    r"\bregla(?:s)?\s+wazuh\b",
    r"\bregla(?:s)?\b",
    r"\brule(?:s)?\b",
    r"\bagente(?:s)?\s+wazuh\b",
    r"\bagente(?:s)?\b",
    r"\bagent(?:s)?\b",
    r"\bendpoint(?:s)?\b",
    r"\bconectad(?:o|os|a|as)\b",
    r"\bconnected\b",
    r"\bdesconectad(?:o|os|a|as)\b",
    r"\bdisconnected\b",
    r"\bevent(?:os?)?\s+seguridad\b",
    r"\bdetección\b",
    r"\bdeteccion\b",
)

def _has_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _extract_ips(text: str) -> list[str]:
    return IPV4_RE.findall(text or "")


def _contains_private_ip(text: str) -> bool:
    for item in _extract_ips(text):
        try:
            if ipaddress.ip_address(item).is_private:
                return True
        except ValueError:
            continue
    return False


def classify_research_intent(user_input: str, objective: str = "") -> dict:
    text = f"{user_input}\n{objective}".lower()
    cve_match = EXACT_CVE_RE.search(text)
    has_latest = _has_any(_LATEST_PATTERNS, text)
    has_vuln = _has_any(_VULN_PATTERNS, text)
    has_network_asset = _has_any(_NETWORK_ASSET_PATTERNS, text) or bool(_extract_ips(text))
    has_compare = _has_any(_COMPARE_PATTERNS, text)
    has_general_web = _has_any(_GENERAL_WEB_PATTERNS, text)
    private_ip = _contains_private_ip(text)

    # Wazuh / SIEM — siempre requiere acceso local a la API
    if _has_any(_WAZUH_PATTERNS, text):
        return {
            "kind": "wazuh_query",
            "route_mode": "wazuh",      # nuevo modo exclusivo
            "requires_research": False,  # no busca en internet
            "private_ip": private_ip,
    }

    if cve_match:
        return {
            "kind": "exact_cve",
            "route_mode": "replace",
            "requires_research": True,
            "cve_id": cve_match.group(0).upper(),
            "private_ip": private_ip,
        }

    if "cve" in text and has_latest:
        return {
            "kind": "latest_cve",
            "route_mode": "replace",
            "requires_research": True,
            "private_ip": private_ip,
        }

    if has_vuln and has_network_asset and private_ip:
        return {
            "kind": "asset_vulnerability_enrichment",
            "route_mode": "augment",
            "requires_research": True,
            "private_ip": private_ip,
        }

    if has_vuln and has_network_asset:
        return {
            "kind": "asset_vulnerability_research",
            "route_mode": "augment",
            "requires_research": True,
            "private_ip": private_ip,
        }

    if has_vuln:
        return {
            "kind": "vulnerability_research",
            "route_mode": "replace",
            "requires_research": True,
            "private_ip": private_ip,
        }

    if has_compare and (has_general_web or has_latest):
        return {
            "kind": "comparative_research",
            "route_mode": "replace",
            "requires_research": True,
            "private_ip": private_ip,
        }

    if has_general_web or has_latest:
        return {
            "kind": "general_web_research",
            "route_mode": "replace",
            "requires_research": True,
            "private_ip": private_ip,
        }

    return {
        "kind": "none",
        "route_mode": "none",
        "requires_research": False,
        "private_ip": private_ip,
    }
