from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote_plus, urlparse

import requests


_ANCHOR_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*>.*?</a>.*?<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_LITE_RE = re.compile(
    r'<a[^>]+class="result-link"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'(?:<td[^>]+class="result-snippet"[^>]*>(?P<snippet>.*?)</td>)?',
    re.IGNORECASE | re.DOTALL,
)
_BING_RESULT_RE = re.compile(
    r'<li[^>]+class="b_algo"[^>]*>.*?<h2[^>]*>.*?'
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'(?:<p[^>]*>(?P<snippet>.*?)</p>)?',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_CVE_ID_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
_LATEST_CVE_QUERY_RE = re.compile(
    r"\b(last|latest|most recent|ultimo|último|ultima|última)\b.*\bcve\b|\bcve\b.*\b(last|latest|most recent|ultimo|último|ultima|última)\b",
    re.IGNORECASE,
)
_JSON_DATE_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE)
_JSON_UPDATED_RE = re.compile(r'"dateUpdated"\s*:\s*"([^"]+)"', re.IGNORECASE)
_JSON_STATE_RE = re.compile(r'"state"\s*:\s*"([^"]+)"', re.IGNORECASE)
_JSON_TITLE_RE = re.compile(r'"cveId"\s*:\s*"([^"]+)"', re.IGNORECASE)

_DOMAIN_SCORES = {
    "cve.org": 100,
    "nvd.nist.gov": 95,
    "cisa.gov": 90,
    "github.com": 70,
}


class WebSearchError(RuntimeError):
    pass


def _strip_html(value: str) -> str:
    return unescape(_TAG_RE.sub("", value or "")).strip()


def _normalize_url(url: str) -> str:
    return unescape(url or "")


def _domain_score(url: str) -> int:
    domain = (urlparse(url).netloc or "").lower()
    for key, score in _DOMAIN_SCORES.items():
        if domain.endswith(key):
            return score
    return 10


def _safe_get(url: str, timeout: int = 20) -> requests.Response:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise WebSearchError(str(exc)) from exc


def _safe_get_json(url: str, timeout: int = 20) -> dict:
    response = _safe_get(url, timeout=timeout)
    try:
        return response.json()
    except ValueError as exc:
        raise WebSearchError(f"JSON invalido desde {url}") from exc


def search_duckduckgo(query: str, max_results: int = 5, timeout: int = 20) -> list[dict]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = _safe_get(url, timeout=timeout)
    html = response.text

    snippets = [_strip_html(match.group("snippet")) for match in _SNIPPET_RE.finditer(html)]
    results: list[dict] = []
    for index, match in enumerate(_ANCHOR_RE.finditer(html)):
        href = _normalize_url(match.group("href"))
        title = _strip_html(match.group("title"))
        if title and href:
            results.append({
                "title": title,
                "url": href,
                "snippet": snippets[index] if index < len(snippets) else "",
                "source_quality": _domain_score(href),
            })
        if len(results) >= max_results:
            break

    return sorted(results, key=lambda item: item["source_quality"], reverse=True)


def search_duckduckgo_lite(query: str, max_results: int = 5, timeout: int = 20) -> list[dict]:
    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    response = _safe_get(url, timeout=timeout)
    results: list[dict] = []
    for match in _DDG_LITE_RE.finditer(response.text):
        href = _normalize_url(match.group("href"))
        title = _strip_html(match.group("title"))
        snippet = _strip_html(match.group("snippet") or "")
        if title and href:
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "source_quality": _domain_score(href),
            })
        if len(results) >= max_results:
            break
    return sorted(results, key=lambda item: item["source_quality"], reverse=True)


def search_bing(query: str, max_results: int = 5, timeout: int = 20) -> list[dict]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    response = _safe_get(url, timeout=timeout)
    results: list[dict] = []
    for match in _BING_RESULT_RE.finditer(response.text):
        href = _normalize_url(match.group("href"))
        title = _strip_html(match.group("title"))
        snippet = _strip_html(match.group("snippet") or "")
        if title and href and not href.startswith("javascript:"):
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "source_quality": _domain_score(href),
            })
        if len(results) >= max_results:
            break
    return sorted(results, key=lambda item: item["source_quality"], reverse=True)


def fetch_page_summary(url: str, timeout: int = 20) -> dict:
    response = _safe_get(url, timeout=timeout)
    text = response.text
    title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    title = _strip_html(title_match.group(1)) if title_match else url
    body_text = _strip_html(text)[:1200]
    return {
        "url": url,
        "title": title,
        "excerpt": body_text,
    }


def _enrich_results_with_pages(results: list[dict], timeout: int = 20) -> list[dict]:
    enriched: list[dict] = []
    for item in results:
        updated = dict(item)
        url = updated.get("url", "")
        if url and not url.lower().endswith(".pdf"):
            try:
                summary = fetch_page_summary(url, timeout=timeout)
                updated["page_title"] = summary.get("title", "")
                updated["page_excerpt"] = summary.get("excerpt", "")
            except WebSearchError:
                updated["page_excerpt"] = ""
        enriched.append(updated)
    return enriched


def lookup_exact_cve(cve_id: str, timeout: int = 20) -> dict:
    cve_id = cve_id.upper()
    api_url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
    data = _safe_get_json(api_url, timeout=timeout)
    vulns = data.get("vulnerabilities", []) or []
    if not vulns:
        raise WebSearchError(f"No se encontro {cve_id} en NVD.")
    record = vulns[0].get("cve", {}) if vulns else {}
    descriptions = record.get("descriptions", []) or []
    metrics = record.get("metrics", {}) or {}
    weaknesses = record.get("weaknesses", []) or []
    configurations = record.get("configurations", []) or []

    description = ""
    for item in descriptions:
        if item.get("lang") == "en":
            description = item.get("value", "")
            break
    if not description and descriptions:
        description = descriptions[0].get("value", "")

    references = search_duckduckgo(
        f'"{cve_id}" site:nvd.nist.gov OR site:cve.org OR site:cisa.gov',
        max_results=8,
        timeout=timeout,
    )

    return {
        "kind": "exact_cve",
        "cve_id": cve_id,
        "query": cve_id,
        "source": "nvd",
        "primary_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
        "title": cve_id,
        "date_published": record.get("published"),
        "date_updated": record.get("lastModified"),
        "state": record.get("vulnStatus"),
        "description": description,
        "metrics": metrics,
        "weaknesses": weaknesses,
        "configurations": configurations,
        "references": references,
        "page_excerpt": description[:1500],
    }


def _search_latest_published_from_nvd(max_results: int = 5, timeout: int = 20) -> list[dict]:
    now = datetime.now(timezone.utc)
    windows = [7, 30, 120, 365]
    aggregated: list[dict] = []
    seen_ids: set[str] = set()
    for days in windows:
        start = (now - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
        end = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        start_index = 0
        page_size = 200
        total_results = None
        while total_results is None or start_index < total_results:
            api_url = (
                "https://services.nvd.nist.gov/rest/json/cves/2.0"
                f"?pubStartDate={quote_plus(start)}&pubEndDate={quote_plus(end)}"
                f"&resultsPerPage={page_size}&startIndex={start_index}"
            )
            data = _safe_get_json(api_url, timeout=timeout)
            total_results = int(data.get("totalResults", 0) or 0)
            vulns = data.get("vulnerabilities", []) or []
            if not vulns:
                break
            for item in vulns:
                cve = item.get("cve", {}) or {}
                cve_id = cve.get("id")
                if not cve_id or cve_id in seen_ids:
                    continue
                seen_ids.add(cve_id)
                descriptions = cve.get("descriptions", []) or []
                description = ""
                for desc in descriptions:
                    if desc.get("lang") == "en":
                        description = desc.get("value", "")
                        break
                aggregated.append({
                    "cve_id": cve_id,
                    "published": cve.get("published"),
                    "lastModified": cve.get("lastModified"),
                    "vulnStatus": cve.get("vulnStatus"),
                    "description": description,
                    "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                })
            start_index += page_size
            if len(aggregated) >= max_results * 20:
                break
        if aggregated:
            break

    aggregated = sorted(
        aggregated,
        key=lambda item: item.get("published") or "",
        reverse=True,
    )
    return aggregated[:max_results]


def search_latest_cve(max_results: int = 5, timeout: int = 20, original_query: str = "", mode: str = "published") -> dict:
    latest_records = _search_latest_published_from_nvd(max_results=max_results, timeout=timeout)
    cve_ids = [item["cve_id"] for item in latest_records]

    return {
        "kind": "latest_cve",
        "query": original_query or "latest CVE",
        "source": "nvd",
        "latest_cve": cve_ids[0] if cve_ids else None,
        "cve_ids": cve_ids[:max_results],
        "results": latest_records,
        "mode": mode,
        "note": (
            "Resultado derivado de los registros publicados mas recientes disponibles a traves de NVD."
        ),
        "ambiguity": (
            "La fecha de descubrimiento real puede diferir de la fecha de publicacion del registro CVE."
        ),
    }


def search_cve_by_keywords(query: str, max_results: int = 5, timeout: int = 20) -> dict:
    refined_queries = [
        f'site:cve.org/CVERecord/SearchResults "{query}"',
        f'site:cve.org/CVERecord "{query}"',
        f'site:nvd.nist.gov/vuln/detail "{query}"',
    ]
    aggregated: list[dict] = []
    seen: set[str] = set()
    for refined in refined_queries:
        for item in search_duckduckgo(refined, max_results=max_results, timeout=timeout):
            if item["url"] not in seen:
                seen.add(item["url"])
                aggregated.append(item)

    cve_ids: list[str] = []
    for item in aggregated:
        for match in _CVE_ID_RE.findall(json.dumps(item, ensure_ascii=False)):
            normalized = match.upper()
            if normalized not in cve_ids:
                cve_ids.append(normalized)

    return {
        "kind": "keyword_cve",
        "query": query,
        "source": "multi",
        "results": sorted(aggregated, key=lambda item: item["source_quality"], reverse=True)[:max_results],
        "cve_ids": cve_ids[:max_results],
    }


def search_general_web(query: str, max_results: int = 8, timeout: int = 20) -> dict:
    results: list[dict] = []
    for searcher in (search_duckduckgo, search_duckduckgo_lite, search_bing):
        try:
            results = searcher(query, max_results=max_results, timeout=timeout)
        except WebSearchError:
            results = []
        if results:
            break

    results = _enrich_results_with_pages(results[:max_results], timeout=timeout)
    return {
        "kind": "general_web",
        "query": query,
        "results": results,
        "top_results": results[:5],
    }


def search_security_topic(query: str, max_results: int = 8, timeout: int = 20) -> dict:
    queries = [
        query,
        f"{query} vulnerability advisory",
        f"{query} cve",
    ]
    aggregated: list[dict] = []
    seen: set[str] = set()
    for refined in queries:
        for item in search_duckduckgo(refined, max_results=max_results, timeout=timeout):
            url = item.get("url", "")
            if url and url not in seen:
                seen.add(url)
                aggregated.append(item)
    aggregated = sorted(aggregated, key=lambda item: item["source_quality"], reverse=True)
    cve_ids: list[str] = []
    for item in aggregated:
        for match in _CVE_ID_RE.findall(json.dumps(item, ensure_ascii=False)):
            normalized = match.upper()
            if normalized not in cve_ids:
                cve_ids.append(normalized)
    return {
        "kind": "security_topic",
        "query": query,
        "results": aggregated[:max_results],
        "cve_ids": cve_ids[:max_results],
    }
