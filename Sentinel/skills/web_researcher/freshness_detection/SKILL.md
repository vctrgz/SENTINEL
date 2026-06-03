name: freshness_detection

# Skill: freshness_detection

## Description
Decide whether a request requires current web information or can be answered from local reasoning and already available context.

---

## Rules
- Always resolve the current date and time before making the decision
- Trigger web search only when freshness materially changes the answer
- Strong triggers include: "latest", "today", "current", "hasta la fecha", "all known CVEs", public disclosures, advisories, and release-dependent facts
- If the request is timeless or local-only, do not browse

---

## Output Expectations
- `requires_web_research: true|false`
- `reason: string`

---

## Failure Modes
- If a request mentions vulnerabilities without asking for current/public data, do not assume web access is required
