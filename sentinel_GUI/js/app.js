const i18n = {
  current: 'es',
  dict: {
    es: {
      dashboard: 'Dashboard', alerts: 'Alertas', agents: 'Agentes', events: 'Eventos',
      rules: 'Reglas XML', settings: 'Ajustes', logout: 'Cerrar Sesión',
      welcome: 'BIENVENIDO AL SISTEMA', searchPlaceholder: 'Buscar en todo el sistema...'
    },
    ca: {
      dashboard: 'Panell', alerts: 'Alertes', agents: 'Agents', events: 'Esdeveniments',
      rules: 'Regles XML', settings: 'Ajustos', logout: 'Tancar Sessió',
      welcome: 'BENVINGUT AL SISTEMA', searchPlaceholder: 'Cercar en tot el sistema...'
    },
    en: {
      dashboard: 'Dashboard', alerts: 'Alerts', agents: 'Agents', events: 'Events',
      rules: 'XML Rules', settings: 'Settings', logout: 'Logout',
      welcome: 'WELCOME TO THE SYSTEM', searchPlaceholder: 'Search across the system...'
    }
  },
  t(key) { return this.dict[this.current][key] || key; },
  update() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = this.t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      el.placeholder = this.t(el.dataset.i18nPlaceholder);
    });
    document.documentElement.lang = this.current;
  }
};

const auth = {
  users: [
    { username: 'admin', password: 'admin', role: 'admin', name: 'Administrator' },
    { username: 'nadia', password: '1234', role: 'technician', name: 'Nadia' }
  ],
  current: null,
  
  init() {
    const saved = localStorage.getItem('sentinel_session');
    if (saved) {
      this.current = JSON.parse(saved);
      this.enter();
    }
    document.getElementById('loginForm').addEventListener('submit', (e) => {
      e.preventDefault();
      this.login();
    });
  },
  
  login() {
    const u = document.getElementById('username').value;
    const p = document.getElementById('password').value;
    const user = this.users.find(x => x.username === u && x.password === p);
    if (user) {
      this.current = user;
      localStorage.setItem('sentinel_session', JSON.stringify(user));
      this.enter();
    } else {
      document.getElementById('loginError').classList.remove('d-none');
      setTimeout(() => document.getElementById('loginError').classList.add('d-none'), 3000);
    }
  },
  
  enter() {
    document.getElementById('loginScreen').classList.add('d-none');
    document.getElementById('app').classList.remove('d-none');
    document.getElementById('sidebarUsername').textContent = this.current.name;
    document.getElementById('sidebarRole').textContent = this.current.role.toUpperCase();
    document.getElementById('headerWelcome').textContent = this.current.name.toUpperCase();
    
    if (this.current.role !== 'admin') {
      document.querySelectorAll('.admin-only').forEach(el => el.classList.add('d-none'));
    }
    
    ui.init();
    dashboard.init();
    agents.init();
    alerts.init();
    events.init();
    rules.init();
    settings.init();
    i18n.update();
  },
  
  logout() {
    this.current = null;
    localStorage.removeItem('sentinel_session');
    location.reload();
  }
};

const router = {
  navigate(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`)?.classList.add('active');
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-link[data-page="${page}"]`)?.classList.add('active');
    
    if (page === 'dashboard') dashboard.render();
    if (page === 'agents') agents.render();
    if (page === 'alerts') alerts.render();
    if (page === 'events') events.render();
    
    document.getElementById('sidebar').classList.remove('open');
  }
};

const ui = {
  notifications: [],
  
  init() {
    document.getElementById('menuToggle').addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('open');
    });
    
    // Polling de alertas reales cada 30 segundos
    setInterval(() => alerts.poll(), 30000);
  },
  
  toggleNotifications() {
    document.getElementById('notifPanel').classList.toggle('d-none');
  },
  
  clearNotifications() {
    this.notifications = [];
    this.renderNotifications();
  },

  // Añade una notificación a partir de una alerta real de OpenSearch
  pushAlert(alert) {
    const level = alert.level >= 10 ? 'critical' : alert.level >= 5 ? 'warning' : 'info';
    this.notifications.unshift({
      text: `[${alert.agent}] ${alert.description}`,
      level,
      time: new Date().toLocaleTimeString()
    });
    if (this.notifications.length > 10) this.notifications.pop();
    this.renderNotifications();

    const badge = document.getElementById('alertBadge');
    badge.textContent = parseInt(badge.textContent || '0') + 1;
    document.getElementById('notifDot').style.display = 'block';
  },
  
  renderNotifications() {
    const list = document.getElementById('notifList');
    list.innerHTML = this.notifications.map(n => `
      <div class="notif-item ${n.level}">
        <div class="small text-white">${n.text}</div>
        <div class="text-secondary" style="font-size:0.7rem">${n.time}</div>
      </div>
    `).join('');
  },
  
  toggleFilters() {
    alert('Filtros avanzados: Implementar según necesidades de búsqueda global');
  }
};

const dashboard = {
  chart: null,
  
  init() {
    this.render();
  },
  
  async render() {
    const agentsData = JSON.parse(localStorage.getItem('sentinel_agents') || '[]');
    document.getElementById('statAgents').textContent = agentsData.filter(a => a.status === 'active').length;

    // Contador real de alertas de las últimas 24 h
    try {
      const count = await OpenSearchAPI.countAlerts(24);
      document.getElementById('statAlerts').textContent = count;
    } catch {
      document.getElementById('statAlerts').textContent = '—';
    }
    
    const ctx = document.getElementById('trafficChart');
    if (!ctx) return;
    if (this.chart) this.chart.destroy();
    
    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ['00:00','04:00','08:00','12:00','16:00','20:00','24:00'],
        datasets: [{
          label: 'Events/sec',
          data: [120, 190, 300, 500, 420, 600, 450],
          borderColor: '#00f3ff',
          backgroundColor: 'rgba(0, 243, 255, 0.1)',
          borderWidth: 2,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#00f3ff',
          pointBorderColor: '#fff',
          pointHoverRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8aa8c9' } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8aa8c9' } }
        }
      }
    });
    
    const legend = document.getElementById('osLegend');
    legend.innerHTML = `
      <div class="legend-item"><div class="legend-dot" style="background:#00f3ff"></div>Linux</div>
      <div class="legend-item"><div class="legend-dot" style="background:#0066ff"></div>Windows</div>
      <div class="legend-item"><div class="legend-dot" style="background:#ff00ff"></div>macOS</div>
    `;
  }
};

const agents = {
  data: [],
  
  async init() {
    try {
      const res = await WazuhAPI.getAgents();
      this.data = res.data.affected_items
        .filter(a => a.id !== '000')  // excluir el manager (no es un agente real)
        .map(a => ({
          id:            a.id,
          name:          a.name,
          ip:            a.ip || a.registerIP || 'N/A',
          status:        a.status,
          os:            WazuhAPI.parseOS((a.os && a.os.name) ? a.os.name : ''),
          osFull:        (a.os && a.os.name) ? a.os.name : (a.os && a.os.platform) ? a.os.platform : 'Unknown',
          version:       a.version || 'N/A',
          dateAdd:       a.dateAdd   || 'N/A',
          lastKeepAlive: a.lastKeepAlive || 'Never'
        }));
      localStorage.setItem('sentinel_agents', JSON.stringify(this.data));
    } catch (err) {
      console.error('[Agents] Error cargando agentes de Wazuh:', err);
      // Intentar recuperar caché local si la API no responde
      const cached = localStorage.getItem('sentinel_agents');
      if (cached) this.data = JSON.parse(cached);
    }
    this.render();
  },
  
  render() {
    const search = document.getElementById('agentSearch')?.value.toLowerCase() || '';
    const os = document.getElementById('agentOsFilter')?.value || '';
    const status = document.getElementById('agentStatusFilter')?.value || '';
    const version = document.getElementById('agentVersionFilter')?.value || '';
    const date = document.getElementById('agentDateFilter')?.value || '';
    
    let filtered = this.data.filter(a => {
      return (!search || a.name.toLowerCase().includes(search) || a.ip.includes(search)) &&
             (!os || a.os === os) &&
             (!status || a.status === status) &&
             (!version || a.version === version) &&
             (!date || a.dateAdd === date);
    });
    
    const grid = document.getElementById('agentsGrid');
    grid.innerHTML = filtered.map(a => `
      <div class="col-md-4 col-lg-3">
        <div class="agent-card" onclick="agents.showDetail('${a.id}')">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <h5 class="mb-0 text-cyan">${a.name}</h5>
            <span class="agent-status status-${a.status}"></span>
          </div>
          <div class="small text-secondary mb-1"><i class="bi bi-hdd-network"></i> ${a.ip}</div>
          <div class="small text-secondary mb-1"><i class="bi bi-cpu"></i> ${a.osFull}</div>
          <div class="small text-secondary"><i class="bi bi-clock-history"></i> ${a.lastKeepAlive}</div>
          <div class="mt-2">
            <span class="badge bg-dark border border-secondary text-secondary">${a.version}</span>
            <span class="badge bg-dark border ${a.status === 'active' ? 'border-success text-success' : a.status === 'disconnected' ? 'border-danger text-danger' : 'border-warning text-warning'} ms-1">
              ${a.status.toUpperCase()}
            </span>
          </div>
        </div>
      </div>
    `).join('');
  },
  
  showDetail(id) {
    const a = this.data.find(x => x.id === id);
    if (!a) return;
    document.getElementById('modalAgentName').textContent = a.name;
    document.getElementById('modalAgentBody').innerHTML = `
      <div class="row g-3">
        <div class="col-6"><strong>ID:</strong> ${a.id}</div>
        <div class="col-6"><strong>IP:</strong> ${a.ip}</div>
        <div class="col-6"><strong>OS:</strong> ${a.osFull}</div>
        <div class="col-6"><strong>Versión Wazuh:</strong> ${a.version}</div>
        <div class="col-6"><strong>Estado:</strong> <span class="text-${a.status === 'active' ? 'success' : a.status === 'disconnected' ? 'danger' : 'warning'}">${a.status.toUpperCase()}</span></div>
        <div class="col-6"><strong>Registrado:</strong> ${a.dateAdd}</div>
        <div class="col-12"><strong>Último KeepAlive:</strong> ${a.lastKeepAlive}</div>
        <div class="col-12 mt-3">
          <button class="glass-btn-sm me-2" onclick="alert('Reiniciando agente ${a.name}...')"><i class="bi bi-arrow-clockwise"></i> Reiniciar</button>
          <button class="glass-btn-sm" onclick="alert('Generando inventario de ${a.name}')"><i class="bi bi-clipboard-data"></i> Inventario</button>
        </div>
      </div>
    `;
    new bootstrap.Modal(document.getElementById('agentModal')).show();
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// ALERTS — Integración real con OpenSearch (índice wazuh-alerts-4.x-*)
// ─────────────────────────────────────────────────────────────────────────────
const alerts = {
  data: [],             // todas las alertas cargadas
  _lastTimestamp: null, // para detectar alertas nuevas en el poll

  // Carga inicial: llama a la API y renderiza
  async init() {
    this._showLoading(true);
    try {
      this.data = await OpenSearchAPI.getAlerts(null, 24, 200);
      if (this.data.length > 0) {
        this._lastTimestamp = this.data[0].timestamp;
      }
      // Actualizar badge del sidebar con el total
      document.getElementById('alertBadge').textContent = this.data.length;
    } catch (err) {
      console.error('[Alerts] Error cargando alertas desde OpenSearch:', err);
      this.data = [];
    }
    this._showLoading(false);
    this.render();
  },

  // Poll periódico (cada 30 s) — llamado desde ui.init()
  async poll() {
    try {
      // Pedimos sólo la última hora para minimizar carga
      const fresh = await OpenSearchAPI.getAlerts(null, 1, 50);
      if (!fresh.length) return;

      // Detectar alertas nuevas (timestamp más reciente que el último guardado)
      const lastSeen = this.data[0]?.id;
      const newAlerts = fresh.filter(a => a.id !== lastSeen && !this.data.find(d => d.id === a.id));

      if (newAlerts.length > 0) {
        // Prepender al array existente y recortar a 200
        this.data = [...newAlerts, ...this.data].slice(0, 200);
        this._lastTimestamp = this.data[0].timestamp;

        // Notificar en el panel lateral la alerta más grave nueva
        const topAlert = newAlerts.reduce((max, a) => a.level > max.level ? a : max, newAlerts[0]);
        ui.pushAlert(topAlert);

        // Si la página de alertas está activa, re-renderizar
        if (document.getElementById('page-alerts')?.classList.contains('active')) {
          this.render();
        }
      }
    } catch (err) {
      console.warn('[Alerts] Error en poll:', err);
    }
  },

  // Carga alertas filtradas por agente (llamado desde el selector en el HTML)
  async filterByAgent(agentId) {
    this._showLoading(true);
    try {
      this.data = await OpenSearchAPI.getAlerts(agentId || null, 24, 200);
    } catch (err) {
      console.error('[Alerts] Error filtrando por agente:', err);
    }
    this._showLoading(false);
    this.render();
  },

  // Renderiza la tabla con el filtro de nivel actual
  render() {
    const levelFilter = document.getElementById('alertLevelFilter')?.value;
    let filtered = this.data;

    if (levelFilter !== '' && levelFilter !== undefined) {
      const lvl = parseInt(levelFilter);
      filtered = filtered.filter(a => a.level === lvl);
    }

    const tbody = document.getElementById('alertsTableBody');
    if (!tbody) return;

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-secondary py-4">
            <i class="bi bi-shield-check me-2"></i>No hay alertas en las últimas 24 horas
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(a => `
      <tr>
        <td class="font-monospace text-cyan" style="font-size:0.75rem">${a.id.substring(0, 12)}…</td>
        <td>${a.agent}</td>
        <td title="${a.description}">${a.description.length > 60 ? a.description.substring(0, 60) + '…' : a.description}</td>
        <td>
          <span class="badge ${a.level >= 10 ? 'bg-danger' : a.level >= 7 ? 'bg-warning text-dark' : a.level >= 4 ? 'bg-info text-dark' : 'bg-secondary'}">
            ${a.level}
          </span>
        </td>
        <td class="small text-secondary">${a.timestamp}</td>
        <td>
          <span class="badge bg-dark border ${
            a.status === 'New'      ? 'border-danger text-danger'   :
            a.status === 'Active'   ? 'border-warning text-warning' :
                                      'border-success text-success'
          }">${a.status}</span>
        </td>
      </tr>
    `).join('');
  },

  _showLoading(show) {
    const tbody = document.getElementById('alertsTableBody');
    if (!tbody) return;
    if (show) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-secondary py-4">
            <span class="spinner-border spinner-border-sm me-2"></span>Cargando alertas desde OpenSearch…
          </td>
        </tr>`;
    }
  }
};

const events = {
  logs: [],
  
  init() {
    this.generateLogs();
    this.render();
    setInterval(() => { this.addLog(); this.render(); }, 2000);
  },
  
  generateLogs() {
    const bases = [
      { type: 'info', text: 'wazuh-analysisd: INFO: Started (pid: 1234).' },
      { type: 'warn', text: 'wazuh-syscheckd: WARN: File integrity monitoring scan completed.' },
      { type: 'error', text: 'wazuh-authd: ERROR: Invalid request for agent key.' },
      { type: 'info', text: 'wazuh-remoted: INFO: (1409): Authentication file changed.' }
    ];
    for (let i = 0; i < 20; i++) {
      const b = bases[Math.floor(Math.random() * bases.length)];
      this.logs.push({ ...b, time: new Date(Date.now() - i * 60000).toISOString() });
    }
  },
  
  addLog() {
    const texts = [
      { type: 'info', text: `wazuh-analysisd: INFO: Rule 5716 matched. Src IP: 10.0.0.${Math.floor(Math.random()*255)}.` },
      { type: 'warn', text: 'wazuh-syscheckd: WARN: Registry value modified.' },
      { type: 'error', text: 'wazuh-authd: ERROR: Agent key already in use.' },
      { type: 'info', text: 'wazuh-monitord: INFO: Report completed.' }
    ];
    const t = texts[Math.floor(Math.random() * texts.length)];
    this.logs.unshift({ ...t, time: new Date().toISOString() });
    if (this.logs.length > 50) this.logs.pop();
  },
  
  render() {
    const term = document.getElementById('terminalBody');
    term.innerHTML = this.logs.map(l => {
      const color = l.type === 'info' ? 'term-info' : l.type === 'warn' ? 'term-warn' : 'term-error';
      const time = new Date(l.time).toLocaleTimeString();
      return `<div class="terminal-line"><span class="term-time">[${time}]</span><span class="${color}">${l.text}</span></div>`;
    }).join('');
    term.scrollTop = term.scrollHeight;
  }
};

const rules = {
  async init() {
    try {
      const xml = await WazuhAPI.getRules();
      document.getElementById('xmlEditor').value = xml;
      this.updateLines();
    } catch (err) {
      console.error('[Rules] Error cargando reglas:', err);
      document.getElementById('xmlEditor').value = '';
      this.updateLines();
    }
  },
  
  updateLines() {
    const textarea = document.getElementById('xmlEditor');
    const lines = textarea.value.split('\n').length;
    document.getElementById('lineNumbers').innerHTML = Array(lines).fill(0).map((_, i) => i + 1).join('<br>');
  },
  
  syncScroll() {
    const textarea = document.getElementById('xmlEditor');
    document.getElementById('lineNumbers').scrollTop = textarea.scrollTop;
  },
  
  async loadFromAPI() {
    document.getElementById('xmlStatus').textContent = 'Loading from Wazuh Manager...';
    const xml = await WazuhAPI.getRules();
    document.getElementById('xmlEditor').value = xml;
    this.updateLines();
    document.getElementById('xmlStatus').textContent = 'Loaded from API';
    setTimeout(() => document.getElementById('xmlStatus').textContent = 'Ready', 2000);
  },
  
  async save() {
    const content = document.getElementById('xmlEditor').value;
    document.getElementById('xmlStatus').textContent = 'Validating XML...';
    if (!content.includes('<group') || !content.includes('</group>')) {
      document.getElementById('xmlStatus').textContent = 'Error: Invalid XML structure';
      document.getElementById('xmlStatus').style.color = 'var(--neon-red)';
      return;
    }
    const res = await WazuhAPI.updateRules(content);
    document.getElementById('xmlStatus').textContent = res.message;
    document.getElementById('xmlStatus').style.color = 'var(--neon-green)';
    setTimeout(() => {
      document.getElementById('xmlStatus').textContent = 'Ready';
      document.getElementById('xmlStatus').style.color = '';
    }, 3000);
  }
};

const settings = {
  init() {
    document.getElementById('langSelect').value = i18n.current;
    this.renderUsers();
  },
  
  toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('sentinel_theme', next);
  },
  
  changeLang(lang) {
    i18n.current = lang;
    localStorage.setItem('sentinel_lang', lang);
    i18n.update();
  },
  
  changePassword() {
    const current = document.getElementById('currentPass').value;
    const newP = document.getElementById('newPass').value;
    const user = auth.users.find(u => u.username === auth.current.username);
    if (user.password !== current) {
      alert('Contraseña actual incorrecta');
      return;
    }
    user.password = newP;
    alert('Contraseña actualizada correctamente');
    document.getElementById('currentPass').value = '';
    document.getElementById('newPass').value = '';
  },
  
  createUser() {
    const name = document.getElementById('newUserName').value;
    const pass = document.getElementById('newUserPass').value;
    const role = document.getElementById('newUserRole').value;
    if (!name || !pass) return alert('Completa todos los campos');
    auth.users.push({ username: name, password: pass, role, name });
    this.renderUsers();
    document.getElementById('newUserName').value = '';
    document.getElementById('newUserPass').value = '';
  },
  
  renderUsers() {
    const tbody = document.getElementById('usersTable');
    tbody.innerHTML = auth.users.map((u, i) => `
      <tr>
        <td class="text-cyan">${u.username}</td>
        <td><span class="badge ${u.role === 'admin' ? 'bg-danger' : 'bg-info text-dark'}">${u.role}</span></td>
        <td class="text-end">
          ${u.username !== 'admin' ? `<button class="btn btn-link text-danger p-0 small" onclick="settings.deleteUser(${i})"><i class="bi bi-trash"></i></button>` : ''}
        </td>
      </tr>
    `).join('');
  },
  
  deleteUser(index) {
    if (confirm('¿Eliminar usuario?')) {
      auth.users.splice(index, 1);
      this.renderUsers();
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const savedTheme = localStorage.getItem('sentinel_theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
  const savedLang = localStorage.getItem('sentinel_lang');
  if (savedLang) i18n.current = savedLang;
  
  auth.init();
});
