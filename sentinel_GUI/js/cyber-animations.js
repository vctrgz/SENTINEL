/**
 * WazuhAPI — Conexión real con la API REST de Wazuh
 * ─────────────────────────────────────────────────
 * • Autenticación JWT contra /security/user/authenticate
 * • Renovación automática del token antes de que caduque
 *   (el JWT de Wazuh dura 900 s por defecto; renovamos a los 840 s)
 * • Reintento automático si una llamada devuelve 401 (token expirado
 *   de forma inesperada): se re-autentica y reintenta 1 vez.
 * • getAlerts() usa ÚNICAMENTE la API REST de Wazuh (:55000).
 *   NO depende de OpenSearch/Elasticsearch (:9200).
 * • Todos los métodos conservan la misma firma que la versión mock
 *   para que app.js no necesite cambios.
 */

const WazuhAPI = (() => {

  // ── Configuración ──────────────────────────────────────────────────────────
  const BASE_URL        = 'https://10.30.212.43:55000';
  const API_USER        = 'grupo07';
  const API_PASS        = 'Grupo_07_';
  const TOKEN_TTL_MS    = 900 * 1000;   // vida del JWT: 900 s
  const RENEW_BEFORE_MS =  60 * 1000;   // renovar 60 s antes de que expire

  // ── Estado interno ─────────────────────────────────────────────────────────
  let _token        = null;
  let _tokenExpires = 0;
  let _renewTimer   = null;

  // ── Obtención y renovación del token ──────────────────────────────────────

  async function _fetchToken() {
    const credentials = btoa(`${API_USER}:${API_PASS}`);

    // Wazuh >= 4.x recomienda POST; fallback a GET si devuelve 405
    let response = await fetch(`${BASE_URL}/security/user/authenticate`, {
      method: 'POST',
      headers: {
        'Authorization': `Basic ${credentials}`,
        'Content-Type': 'application/json'
      }
    });

    if (response.status === 405) {
      response = await fetch(`${BASE_URL}/security/user/authenticate`, {
        method: 'GET',
        headers: {
          'Authorization': `Basic ${credentials}`,
          'Content-Type': 'application/json'
        }
      });
    }

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Wazuh auth failed (${response.status}): ${body}`);
    }

    const data = await response.json();
    _token        = data.data.token;
    _tokenExpires = Date.now() + TOKEN_TTL_MS;

    console.info('[WazuhAPI] Token obtenido. Expira en', TOKEN_TTL_MS / 1000, 's');
    _scheduleRenewal();
    return _token;
  }

  function _scheduleRenewal() {
    if (_renewTimer) clearTimeout(_renewTimer);
    const delay = TOKEN_TTL_MS - RENEW_BEFORE_MS; // 840 000 ms
    _renewTimer = setTimeout(async () => {
      console.info('[WazuhAPI] Renovando token automáticamente…');
      try {
        await _fetchToken();
      } catch (err) {
        console.error('[WazuhAPI] Error en renovación automática:', err);
        _token = null;
      }
    }, delay);
  }

  async function _getToken() {
    if (!_token || Date.now() >= _tokenExpires) {
      await _fetchToken();
    }
    return _token;
  }

  // ── Wrapper genérico de peticiones ────────────────────────────────────────

  async function _request(path, options = {}, _retry = true) {
    const token = await _getToken();

    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });

    if (response.status === 401 && _retry) {
      console.warn('[WazuhAPI] 401 inesperado; forzando renovación de token…');
      _token = null;
      return _request(path, options, false);
    }

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Wazuh API ${response.status} en ${path}: ${body}`);
    }

    return response.json();
  }

  // ── Helpers privados ───────────────────────────────────────────────────────

  function _resolveOsName(agent) {
    const os = agent.os || {};
    if (os.name)     return os.name;
    if (os.platform) return os.platform;
    return 'Unknown';
  }

  /**
   * Normaliza una alerta cruda de la API REST al formato que espera app.js:
   * { id, agent, description, level, timestamp, status }
   */
  function _normalizeAlert(raw) {
    // /manager/logs  →  { timestamp, tag, level, description }
    // /alerts        →  { id, rule: { level, description }, agent: { name }, timestamp }
    if (raw.rule) {
      // Formato /alerts
      return {
        id:          raw.id          || raw['_id'] || Math.random().toString(36).slice(2),
        agent:       raw.agent?.name || raw.manager?.name || 'manager',
        description: raw.rule?.description || raw.rule?.id || '—',
        level:       Number(raw.rule?.level ?? 0),
        timestamp:   raw.timestamp   || new Date().toISOString(),
        status:      'New'
      };
    }
    // Formato /manager/logs
    const levelMap = { info: 1, warning: 2, error: 3, critical: 4 };
    return {
      id:          Math.random().toString(36).slice(2),
      agent:       'manager',
      description: raw.description || raw.plain_log || '—',
      level:       levelMap[raw.level?.toLowerCase()] ?? 1,
      timestamp:   raw.timestamp   || new Date().toISOString(),
      status:      'New'
    };
  }

  // ── API pública (misma interfaz que el mock) ───────────────────────────────

  return {

    baseURL: BASE_URL,

    async authenticate() {
      const token = await _fetchToken();
      return { token };
    },

    async getAgents() {
      const data = await _request('/agents?limit=500');
      if (data?.data?.affected_items) {
        data.data.affected_items = data.data.affected_items.map(agent => ({
          ...agent,
          os: { name: _resolveOsName(agent) }
        }));
      }
      return data;
    },

    /**
     * getAlerts()
     * ───────────
     * Obtiene alertas únicamente a través de la API REST de Wazuh (:55000).
     * NO usa OpenSearch/Elasticsearch (:9200).
     *
     * Estrategia de endpoints (en orden de preferencia):
     *   1. GET /alerts?limit=100&sort=-timestamp          (Wazuh >= 4.2)
     *   2. GET /manager/logs?limit=100&sort=-timestamp    (fallback universal)
     *
     * La respuesta siempre devuelve el mismo envelope que usaba el mock:
     *   { data: { affected_items: [...], total_affected_items: N } }
     */
    async getAlerts() {
      let raw;

      // ── Intento 1: endpoint nativo de alertas ──────────────────────────────
      try {
        raw = await _request('/alerts?limit=100&sort=-timestamp');
      } catch (err) {
        console.warn('[WazuhAPI] /alerts no disponible, usando /manager/logs:', err.message);
        raw = null;
      }

      // ── Intento 2: logs del manager como fallback ──────────────────────────
      if (!raw?.data?.affected_items?.length) {
        try {
          raw = await _request('/manager/logs?limit=100&sort=-timestamp');
        } catch (err) {
          console.error('[WazuhAPI] /manager/logs también falló:', err.message);
          // Devolver envelope vacío para que app.js no rompa
          return { data: { affected_items: [], total_affected_items: 0 } };
        }
      }

      // ── Normalizar al formato que espera app.js ────────────────────────────
      const items = (raw?.data?.affected_items ?? []).map(_normalizeAlert);

      return {
        data: {
          affected_items:       items,
          total_affected_items: raw?.data?.total_affected_items ?? items.length
        }
      };
    },

    async getRules() {
      const data = await _request(
        '/manager/files?path=etc%2Frules%2Flocal_rules.xml'
      );
      return data?.data?.contents ?? '';
    },

    async updateRules(xmlContent) {
      const data = await _request(
        '/manager/files?path=etc%2Frules%2Flocal_rules.xml',
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/octet-stream' },
          body: xmlContent
        }
      );
      return { message: data?.message ?? 'Rules updated', error: data?.error ?? 0 };
    },

    parseOS(osName = '') {
      if (osName.includes('Windows'))                     return 'Windows';
      if (osName.includes('macOS') || osName.includes('Darwin')) return 'macOS';
      return 'Linux';
    }
  };

})();
