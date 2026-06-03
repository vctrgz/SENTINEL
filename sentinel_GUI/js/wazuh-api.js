/**
 * WazuhAPI — Conexión real con la API REST de Wazuh
 * ─────────────────────────────────────────────────
 * • Autenticación JWT contra /security/user/authenticate
 * • Renovación automática del token antes de que caduque
 *   (el JWT de Wazuh dura 900 s por defecto; renovamos a los 840 s)
 * • Reintento automático si una llamada devuelve 401 (token expirado
 *   de forma inesperada): se re-autentica y reintenta 1 vez.
 */

const WazuhAPI = (() => {

  // ── Configuración ──────────────────────────────────────────────────────────
  const BASE_URL        = 'https://10.30.212.43:55000';
  const API_USER        = 'wazuh';
  const API_PASS        = 'Grupo07!';
  const TOKEN_TTL_MS    = 900 * 1000;     // 900 s (por defecto en Wazuh)
  const RENEW_BEFORE_MS = 60  * 1000;     // renovar 60 s antes de que expire

  // ── Estado interno ─────────────────────────────────────────────────────────
  let _token        = null;
  let _tokenExpires = 0;
  let _renewTimer   = null;

  // ── Obtención y renovación del token ──────────────────────────────────────

  async function _fetchToken() {
    const credentials = btoa(`${API_USER}:${API_PASS}`);
    const response = await fetch(`${BASE_URL}/security/user/authenticate`, {
      method: 'GET',
      headers: {
        'Authorization': `Basic ${credentials}`,
        'Content-Type': 'application/json'
      }
    });

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
    const delay = TOKEN_TTL_MS - RENEW_BEFORE_MS;
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

  // ── Helper privado ─────────────────────────────────────────────────────────

  function _resolveOsName(agent) {
    const os = agent.os || {};
    if (os.name)     return os.name;
    if (os.platform) return os.platform;
    return 'Unknown';
  }

  // ── API pública ────────────────────────────────────────────────────────────

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
      if (osName.includes('Windows')) return 'Windows';
      if (osName.includes('macOS') || osName.includes('Darwin')) return 'macOS';
      return 'Linux';
    }
  };

})();


/**
 * OpenSearchAPI — Consulta de alertas contra el índice wazuh-alerts-4.x-*
 * ─────────────────────────────────────────────────────────────────────────
 * • Autenticación Basic independiente de la API REST de Wazuh
 * • getAlerts(agentId?, hours?, size?) — devuelve alertas normalizadas
 *   listas para usar en el objeto `alerts` de app.js
 *
 * Credenciales: las mismas de admin de OpenSearch (por defecto admin/admin
 * en Wazuh All-In-One). Ajusta OS_USER / OS_PASS si las has cambiado.
 */

const OpenSearchAPI = (() => {

  // ── Configuración ──────────────────────────────────────────────────────────
  const OS_URL  = 'https://10.30.212.43:9200';   // misma IP, puerto 9200
  const OS_USER = 'admin';
  const OS_PASS = 'Grupo07!';                     // ajusta si es diferente
  const INDEX   = 'wazuh-alerts-4.x-*';

  const _authHeader = 'Basic ' + btoa(`${OS_USER}:${OS_PASS}`);

  // ── Helper interno de fetch ────────────────────────────────────────────────

  async function _post(path, body) {
    const response = await fetch(`${OS_URL}${path}`, {
      method: 'POST',
      headers: {
        'Authorization': _authHeader,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`OpenSearch ${response.status} en ${path}: ${text}`);
    }

    return response.json();
  }

  // ── Normalización de un hit de OpenSearch al formato usado en app.js ───────

  function _normalize(hit) {
    const src   = hit._source || {};
    const rule  = src.rule   || {};
    const agent = src.agent  || {};
    const level = rule.level ?? 0;

    // Estado sintético basado en el nivel de la regla
    let status = 'Resolved';
    if (level >= 10) status = 'New';
    else if (level >= 5) status = 'Active';

    return {
      id:          hit._id,
      agent:       agent.name || agent.id || 'Unknown',
      agentId:     agent.id   || '',
      description: rule.description || src.full_log || '—',
      level,
      groups:      rule.groups || [],
      timestamp:   src.timestamp
        ? new Date(src.timestamp).toLocaleString('es-ES')
        : '—',
      status,
      srcip:       (src.data && src.data.srcip) || '',
      location:    src.location || ''
    };
  }

  // ── API pública ────────────────────────────────────────────────────────────

  return {

    /**
     * Obtiene alertas de OpenSearch.
     *
     * @param {string|null} agentId  - ID del agente para filtrar (ej. '001'), o null para todas
     * @param {number}      hours    - Ventana temporal en horas (por defecto 24)
     * @param {number}      size     - Número máximo de alertas (por defecto 200)
     * @returns {Promise<Array>}     - Array de alertas normalizadas
     */
    async getAlerts(agentId = null, hours = 24, size = 200) {
      const mustClauses = [
        { range: { timestamp: { gte: `now-${hours}h`, lte: 'now' } } }
      ];

      if (agentId) {
        mustClauses.push({ match: { 'agent.id': agentId } });
      }

      const query = {
        size,
        sort: [{ timestamp: { order: 'desc' } }],
        query: { bool: { must: mustClauses } },
        _source: [
          'timestamp', 'agent.id', 'agent.name',
          'rule.id', 'rule.description', 'rule.level', 'rule.groups',
          'data.srcip', 'location', 'full_log'
        ]
      };

      const data = await _post(`/${INDEX}/_search`, query);
      const hits = data?.hits?.hits || [];
      return hits.map(_normalize);
    },

    /**
     * Cuenta el total de alertas de las últimas N horas.
     * Útil para el badge del sidebar y el stat del dashboard.
     *
     * @param {number} hours
     * @returns {Promise<number>}
     */
    async countAlerts(hours = 24) {
      const data = await _post(`/${INDEX}/_count`, {
        query: {
          range: { timestamp: { gte: `now-${hours}h`, lte: 'now' } }
        }
      });
      return data?.count ?? 0;
    }
  };

})();
