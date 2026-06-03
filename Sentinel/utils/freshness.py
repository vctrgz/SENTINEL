from __future__ import annotations

import re


_CURRENT_INFO_PATTERNS = (
    r"\bcurrent\b",
    r"\blatest\b",
    r"\bmost recent\b",
    r"\brecent\b",
    r"\bnewest\b",
    r"\bnewly discovered\b",
    r"\bnewly published\b",
    r"\btoday\b",
    r"\bnow\b",
    r"\bas of\b",
    r"\bup[- ]to[- ]date\b",
    r"\bup[- ]to[- ]the[- ]minute\b",
    r"\bhasta la fecha\b",
    r"\ba fecha de hoy\b",
    r"\bactual(?:idad|es)?\b",
    r"\bactualizado(?:s|as)?\b",
    r"\bvigente(?:s)?\b",
    r"\bde hoy\b",
    r"\bhoy\b",
    r"\breciente(?:s)?\b",
    r"\bultim[oa](?:s)?\b",
    r"\búltim[oa](?:s)?\b",
)

_WEB_ONLY_PATTERNS = (
    r"\bcve(?:s)?\b",
    r"\bvulnerabilit(?:y|ies)\b",
    r"\bvulnerabilidad(?:es)?\b",
    r"\badvisories?\b",
    r"\badvisories\b",
    r"\bdisclosure(?:s)?\b",
    r"\bexploit(?:s)?\b",
    r"\b0day\b",
    r"\b0-day\b",
    r"\bnvd\b",
    r"\bcisa\b",
    r"\bcwe(?:s)?\b",
    r"\bnoticias?\b",
    r"\bpublicad[oa]s?\b",
    r"\bdivulgad[oa]s?\b",
    r"\bdescubiert[oa]s?\b",
    r"\bconocid[oa]s?\b",
    r"\bknown to date\b",
    r"\buntil today\b",
    r"\blista de todos los cves\b",
)


def assess_current_info_need(text: str) -> dict:
    normalized = (text or "").lower()
    current_hits = [p for p in _CURRENT_INFO_PATTERNS if re.search(p, normalized)]
    web_hits = [p for p in _WEB_ONLY_PATTERNS if re.search(p, normalized)]

    requires_current_time = bool(current_hits or web_hits)
    requires_web_research = bool(web_hits and current_hits) or "lista de todos los cves" in normalized

    if "cve" in normalized and any(
        token in normalized
        for token in (
            "latest", "current", "hasta la fecha", "hoy", "known to date", "all cves",
            "ultima", "última", "ultimo", "último",
        )
    ):
        requires_web_research = True

    return {
        "requires_current_time": requires_current_time,
        "requires_web_research": requires_web_research,
        "matched_current_patterns": current_hits,
        "matched_web_patterns": web_hits,
    }
