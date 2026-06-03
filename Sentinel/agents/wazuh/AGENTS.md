# Wazuh Agent

## Purpose
Read, analyze, and proactively monitor Wazuh SIEM data
(alerts, logs, rules, agents) using the Wazuh REST API.

## Responsibilities
- Authenticate against Wazuh Manager REST API (JWT)
- Fetch and filter alerts by severity level
- Retrieve manager logs and detection rules
- Monitor agent health and connectivity
- Run proactive background checks for critical alerts

## Routing keywords
- alerts, alertas, críticas, critical, nivel, level
- logs, registros, manager logs
- reglas, rules, detección
- agente, agent, endpoint, wazuh
- siem, evento, event, incidente, incident

## Output format
Always produce structured markdown with:
- Executive summary (1–3 sentences)
- Prioritized findings (by rule level, descending)
- Affected agents
- Recommended actions