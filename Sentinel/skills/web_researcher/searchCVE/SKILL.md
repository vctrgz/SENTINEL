name: searchCVE

# Skill: searchCVE

## Description
Search for CVE identifiers on `https://www.cve.org/` when a product, service, version, or explicit CVE request requires current public vulnerability data.

---

## Rules
- Use cve.org as the primary source for CVE identification
- Build specific queries from product name + version when possible
- If the user asks for the latest/most recent/ultima CVE, do not treat it like a normal keyword search
- Clarify that "ultimo CVE descubierto" is ambiguous because cve.org tracks CVE records/publication, not necessarily the real discovery date
- If the version fingerprint is weak or ambiguous, return `sin evidencia suficiente`
- Never invent CVE IDs to fill gaps
- If no reliable match is found on cve.org, say so and keep the hypothesis open

---

## Recommended Query Patterns
- `<product> <version>`
- `<product> <version> CVE`
- Exact CVE ID when already known
- For latest-CVE requests, search recent `cve.org/CVERecord` entries and state the ambiguity explicitly

---

## Output Expectations
- Query used
- CVE IDs found
- Confidence level
- Note about ambiguity or incomplete evidence when applicable
