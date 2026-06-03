name: source_triage

# Skill: source_triage

## Description
Assess whether a web result is authoritative enough to support a cybersecurity answer.

---

## Rules
- Prefer official program sites, vendor advisories, and standards bodies
- For CVE identification, prioritize cve.org over secondary summaries
- Distinguish authoritative data from commentary or mirrors
- If only weak sources are available, downgrade confidence

---

## Output Expectations
- `source_quality: high|medium|low`
- `reason: string`
