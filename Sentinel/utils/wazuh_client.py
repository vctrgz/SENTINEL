"""
utils/wazuh_client.py

Cliente REST para la API de Wazuh Manager.
Maneja autenticación JWT, refresco de token y los endpoints principales.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import urllib3

from app.config import Config
from utils.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WazuhAuthError(Exception):
    pass


class WazuhAPIError(Exception):
    pass


class WazuhClient:
    """
    Wrapper sobre la REST API de Wazuh (v4+).
    Gestiona el ciclo de vida del JWT (expira cada 15 min).
    """

    TOKEN_TTL = 840  # segundos antes de refrescar (14 min, margen de 1 min)

    def __init__(self) -> None:
        self.host     = (Config.WAZUH_HOST or "").rstrip("/")
        self.user     = Config.WAZUH_USER
        self.password = Config.WAZUH_PASSWORD
        self.verify   = Config.WAZUH_VERIFY_SSL
        self.indexer_url = (Config.WAZUH_INDEXER_URL or self._derive_indexer_url()).rstrip("/")
        self.indexer_user = Config.WAZUH_INDEXER_USER
        self.indexer_password = Config.WAZUH_INDEXER_PASSWORD
        self.alerts_index = Config.WAZUH_ALERTS_INDEX
        self._token: str = ""
        self._token_ts: float = 0.0

    def _derive_indexer_url(self) -> str:
        if not self.host:
            return ""
        parsed = urlparse(self.host)
        if not parsed.scheme or not parsed.netloc:
            return ""
        hostname = parsed.hostname or ""
        netloc = hostname
        if parsed.port:
            netloc = f"{hostname}:9200"
        return urlunparse((parsed.scheme, netloc, "", "", "", ""))

    # ─────────────────────────────────────────────────────────────
    # Auth
    # ─────────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        url = f"{self.host}/security/user/authenticate"
        try:
            resp = requests.get(url, auth=(self.user, self.password), verify=self.verify, timeout=10)
            if resp.status_code in {404, 405}:
                resp = requests.post(url, auth=(self.user, self.password), verify=self.verify, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._token    = data["data"]["token"]
            self._token_ts = time.monotonic()
            logger.info("[WazuhClient] JWT obtenido correctamente.")
        except Exception as exc:
            raise WazuhAuthError(f"Autenticación Wazuh fallida: {exc}") from exc

    def _get_token(self) -> str:
        if not self._token or (time.monotonic() - self._token_ts) > self.TOKEN_TTL:
            self._authenticate()
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ─────────────────────────────────────────────────────────────
    # HTTP helpers
    # ─────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.host}{path}"
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params or {},
                verify=self.verify,
                timeout=20,
            )
            if resp.status_code == 401:
                # Token expirado a mitad — refrescar y reintentar una vez
                self._token = ""
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    params=params or {},
                    verify=self.verify,
                    timeout=20,
                )
            resp.raise_for_status()
            return resp.json()
        except WazuhAuthError:
            raise
        except Exception as exc:
            raise WazuhAPIError(f"Error GET {path}: {exc}") from exc

    # ─────────────────────────────────────────────────────────────
    # API endpoints
    # ─────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Comprueba conectividad básica."""
        if not self.host or not self.user or not self.password:
            return False
        try:
            self._authenticate()
            return True
        except Exception:
            return False

    def get_alerts(
        self,
        limit: int = 100,
        min_level: int | None = None,
        agent_id: str | None = None,
    ) -> list[dict]:
        """
        Devuelve alertas recientes.
        min_level: filtra por nivel de regla (0–15, 10+ = crítico)
        """
        params: dict[str, Any] = {
            "limit": min(limit, 500),
            "sort": "-timestamp",
        }
        q_parts = []
        if min_level is not None:
            q_parts.append(f"rule.level>={min_level}")
        if agent_id:
            q_parts.append(f"agent.id={agent_id}")
        if q_parts:
            params["q"] = ",".join(q_parts)

        data = self._get("/alerts", params)
        return data.get("data", {}).get("affected_items", [])

    def get_indexer_alerts(
        self,
        agent_id: str | None = None,
        hours: int = 24,
        limit: int = 100,
        min_level: int | None = None,
    ) -> list[dict]:
        if not self.indexer_url or not self.indexer_user or not self.indexer_password:
            raise WazuhAPIError("Indexer/OpenSearch no configurado.")

        must: list[dict] = [
            {"range": {"timestamp": {"gte": f"now-{max(1, hours)}h", "lte": "now"}}}
        ]
        if agent_id:
            must.append({"match": {"agent.id": agent_id}})
        if min_level is not None:
            must.append({"range": {"rule.level": {"gte": min_level}}})

        payload = {
            "size": min(limit, 500),
            "sort": [{"timestamp": {"order": "desc"}}],
            "query": {"bool": {"must": must}},
            "_source": [
                "timestamp", "agent.id", "agent.name", "agent.ip",
                "rule.id", "rule.description", "rule.level", "rule.groups",
                "data.srcip", "location", "full_log",
            ],
        }
        url = f"{self.indexer_url}/{self.alerts_index}/_search"
        try:
            resp = requests.post(
                url,
                auth=(self.indexer_user, self.indexer_password),
                json=payload,
                verify=self.verify,
                timeout=20,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", []) or []
            return [self._normalize_indexer_alert(hit) for hit in hits]
        except Exception as exc:
            raise WazuhAPIError(f"Error consultando alertas en OpenSearch: {exc}") from exc

    def count_indexer_alerts(self, hours: int = 24, min_level: int | None = None) -> int:
        if not self.indexer_url or not self.indexer_user or not self.indexer_password:
            raise WazuhAPIError("Indexer/OpenSearch no configurado.")
        must: list[dict] = [
            {"range": {"timestamp": {"gte": f"now-{max(1, hours)}h", "lte": "now"}}}
        ]
        if min_level is not None:
            must.append({"range": {"rule.level": {"gte": min_level}}})
        url = f"{self.indexer_url}/{self.alerts_index}/_count"
        try:
            resp = requests.post(
                url,
                auth=(self.indexer_user, self.indexer_password),
                json={"query": {"bool": {"must": must}}},
                verify=self.verify,
                timeout=20,
            )
            resp.raise_for_status()
            return int(resp.json().get("count", 0) or 0)
        except Exception as exc:
            raise WazuhAPIError(f"Error contando alertas en OpenSearch: {exc}") from exc

    def _normalize_indexer_alert(self, hit: dict) -> dict:
        src = hit.get("_source", {}) or {}
        rule = src.get("rule", {}) or {}
        agent = src.get("agent", {}) or {}
        return {
            "id": hit.get("_id", src.get("id", "")),
            "timestamp": src.get("timestamp", ""),
            "agent": {"id": agent.get("id", ""), "name": agent.get("name", "unknown"), "ip": agent.get("ip", "")},
            "rule": {
                "id": rule.get("id", ""),
                "level": rule.get("level", 0),
                "description": rule.get("description", ""),
                "groups": rule.get("groups", []),
            },
            "data": src.get("data", {}) or {},
            "location": src.get("location", ""),
            "full_log": src.get("full_log", ""),
        }

    def get_logs(self, limit: int = 100, log_type: str | None = None) -> list[dict]:
        """Devuelve logs del manager."""
        params: dict[str, Any] = {"limit": min(limit, 500), "sort": "-timestamp"}
        if log_type:
            params["type_log"] = log_type
        data = self._get("/manager/logs", params)
        return data.get("data", {}).get("affected_items", [])

    def get_rules(
        self,
        limit: int = 200,
        rule_ids: list[int] | None = None,
        level: int | None = None,
    ) -> list[dict]:
        """Devuelve reglas de detección."""
        params: dict[str, Any] = {"limit": min(limit, 2000)}
        if rule_ids:
            params["rule_ids"] = ",".join(str(r) for r in rule_ids)
        if level is not None:
            params["level"] = level
        data = self._get("/rules", params)
        return data.get("data", {}).get("affected_items", [])

    def get_agents(self, status: str | None = None) -> list[dict]:
        """Devuelve agentes registrados."""
        params: dict[str, Any] = {"limit": 500}
        if status:
            params["status"] = status
        data = self._get("/agents", params)
        return data.get("data", {}).get("affected_items", [])

    def get_agent_alerts(self, agent_id: str, limit: int = 50) -> list[dict]:
        """Alertas específicas de un agente."""
        return self.get_alerts(limit=limit, agent_id=agent_id)

    def get_critical_alerts(self, limit: int = 50) -> list[dict]:
        """Shortcut: alertas nivel >= Config.WAZUH_ALERT_LEVEL_MIN."""
        try:
            return self.get_indexer_alerts(limit=limit, min_level=Config.WAZUH_ALERT_LEVEL_MIN)
        except WazuhAPIError:
            return self.get_alerts(limit=limit, min_level=Config.WAZUH_ALERT_LEVEL_MIN)
