const sentinel = {
  apiBase: localStorage.getItem('sentinel_ai_api_base') || (
    location.protocol === 'file:' ? 'http://localhost:8000' : location.origin
  ),
  initialized: false,
  busy: false,
  progressEl: null,

  init() {
    if (this.initialized) return;
    this.initialized = true;
    this.ensureSudoModal();
    this.checkHealth();
  },

  endpoint(path) {
    return `${this.apiBase.replace(/\/$/, '')}${path}`;
  },

  async checkHealth() {
    const candidates = [...new Set([
      this.apiBase,
      location.protocol !== 'file:' ? location.origin : null,
      'http://localhost:8001',
      'http://127.0.0.1:8001',
      'http://localhost:8000',
      'http://127.0.0.1:8000',
    ].filter(Boolean))];

    let lastError = null;
    let degraded = null;
    for (const base of candidates) {
      try {
        const response = await fetch(`${base.replace(/\/$/, '')}/health`);
        const data = await response.json();
        if (data.status === 'ok') {
          this.apiBase = base;
          localStorage.setItem('sentinel_ai_api_base', base);
          this.applyHealth(data);
          return;
        }
        degraded = degraded || { base, data };
      } catch (error) {
        lastError = error;
      }
    }

    if (degraded) {
      this.apiBase = degraded.base;
      localStorage.setItem('sentinel_ai_api_base', degraded.base);
      this.applyHealth(degraded.data);
      return;
    }

    this.setHeaderStatus('OFFLINE');
    this.replaceWelcome(
      `No puedo conectar con el backend multiagente. Arranca Sentinel en <code>http://localhost:8000</code> o define <code>sentinel_ai_api_base</code> en localStorage. ${lastError ? this.escapeHtml(lastError.message) : ''}`,
      true
    );
  },

  applyHealth(data) {
    const models = Array.isArray(data.models) && data.models.length
      ? data.models.slice(0, 3).join(', ')
      : 'sin proveedores LLM configurados';

    if (data.status === 'ok') {
      this.setHeaderStatus('ONLINE');
      this.replaceWelcome(
        `Sistema multiagente conectado. Modelos activos: <code>${this.escapeHtml(models)}</code>. Que analisis necesitas ejecutar?`,
        true
      );
    } else {
      this.setHeaderStatus('DEGRADED');
      this.replaceWelcome(
        `Backend conectado, pero no hay proveedores LLM disponibles. Revisa las claves en <code>.env</code>.`,
        true
      );
    }
  },

  setHeaderStatus(status) {
    const statusEl = document.querySelector('#page-sentinel .sentinel-header .small');
    if (statusEl) statusEl.textContent = `NEURAL SECURITY ASSISTANT // ${status}`;
  },

  replaceWelcome(html, trusted = false) {
    const firstBubble = document.querySelector('#sentinelChat .ai-message .message-bubble');
    if (!firstBubble) return;
    firstBubble.innerHTML = trusted ? html : this.escapeHtml(html);
  },

  async send() {
    const input = document.getElementById('sentinelInput');
    const text = input.value.trim();
    if (!text || this.busy) return;

    this.addMessage(text, 'user');
    input.value = '';
    input.disabled = true;
    this.busy = true;
    this.setSendDisabled(true);
    this.progressEl = this.addProgress('Procesando solicitud...');

    try {
      const response = await fetch(this.endpoint('/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      });

      if (!response.ok) {
        const body = await this.readErrorBody(response);
        this.removeProgress();
        this.addMessage(`Error: ${body}`, 'ai');
        return;
      }

      if (!response.body || !response.body.getReader) {
        const body = await response.text();
        this.removeProgress();
        this.addMessage(body || '(sin respuesta)', 'ai');
        return;
      }

      await this.readStream(response.body);
    } catch (error) {
      this.removeProgress();
      this.addMessage(`Error de conexion con el backend multiagente: ${error.message}`, 'ai');
      this.setHeaderStatus('OFFLINE');
    } finally {
      this.busy = false;
      input.disabled = false;
      this.setSendDisabled(false);
      input.focus();
    }
  },

  async readStream(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        this.handleStreamEvent(line.slice(6));
      }
    }
  },

  handleStreamEvent(raw) {
    try {
      const event = JSON.parse(raw);
      if (event.type === 'ping') {
        this.updateProgress(event.message || 'Procesando...');
      } else if (event.type === 'needs_sudo') {
        this.updateProgress('Esperando autenticacion sudo...');
        this.showSudoModal(event.message);
      } else if (event.type === 'done') {
        this.hideSudoModal();
        this.removeProgress();
        this.addMessage(this.renderMarkdown(event.response || '(sin respuesta)'), 'ai', true);
      } else if (event.type === 'error') {
        this.hideSudoModal();
        this.removeProgress();
        this.addMessage(event.response || 'Error interno del agente.', 'ai');
      }
    } catch (error) {
      console.warn('[SentinelAI] Evento SSE invalido:', raw);
    }
  },

  async readErrorBody(response) {
    try {
      const json = await response.json();
      return json.response || json.error || response.statusText;
    } catch {
      return response.statusText;
    }
  },

  addMessage(text, sender, trustedHtml = false) {
    const chat = document.getElementById('sentinelChat');
    const div = document.createElement('div');
    div.className = `chat-message ${sender}-message`;
    div.innerHTML = `
      <div class="message-bubble ${sender === 'ai' ? 'glass-bubble-ai' : ''}">${trustedHtml ? text : this.escapeHtml(text)}</div>
      <span class="message-time">${new Date().toLocaleTimeString()}</span>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  },

  addProgress(text) {
    const chat = document.getElementById('sentinelChat');
    const div = document.createElement('div');
    div.className = 'chat-message ai-message sentinel-progress-message';
    div.innerHTML = `
      <div class="message-bubble glass-bubble-ai">
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        <span class="sentinel-progress-text">${this.escapeHtml(text)}</span>
      </div>
      <span class="message-time">NOW</span>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  },

  updateProgress(text) {
    const target = this.progressEl?.querySelector('.sentinel-progress-text');
    if (target) target.textContent = text;
  },

  removeProgress() {
    if (this.progressEl) {
      this.progressEl.remove();
      this.progressEl = null;
    }
  },

  setSendDisabled(disabled) {
    const button = document.querySelector('#page-sentinel .sentinel-input button');
    if (button) button.disabled = disabled;
  },

  async submitSudoPassword() {
    const input = document.getElementById('sentinelSudoInput');
    const button = document.getElementById('sentinelSudoSubmit');
    const password = input.value.trim();
    if (!password) {
      input.focus();
      return;
    }

    button.disabled = true;
    try {
      const response = await fetch(this.endpoint('/sudo-auth'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      if (!response.ok) throw new Error(response.statusText);
      this.hideSudoModal();
    } catch (error) {
      const errorEl = document.getElementById('sentinelSudoError');
      errorEl.textContent = `Error al enviar la contrasena: ${error.message}`;
      errorEl.classList.remove('d-none');
      input.value = '';
      input.focus();
    } finally {
      button.disabled = false;
    }
  },

  ensureSudoModal() {
    if (document.getElementById('sentinelSudoModal')) return;

    const modal = document.createElement('div');
    modal.id = 'sentinelSudoModal';
    modal.className = 'modal fade';
    modal.tabIndex = -1;
    modal.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content glass-modal">
          <div class="modal-header border-secondary">
            <h5 class="modal-title text-cyan"><i class="bi bi-shield-lock"></i> Autenticacion sudo requerida</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <p id="sentinelSudoDesc" class="text-secondary small mb-3">
              Sentinel AI necesita permisos de superusuario para continuar.
            </p>
            <div id="sentinelSudoError" class="alert alert-danger py-2 d-none"></div>
            <div class="glass-input-group mb-0">
              <input type="password" id="sentinelSudoInput" class="glass-input" placeholder=" " autocomplete="current-password">
              <label>Contrasena del sistema</label>
              <i class="bi bi-key"></i>
            </div>
          </div>
          <div class="modal-footer border-secondary">
            <button type="button" class="glass-btn-sm" data-bs-dismiss="modal">Cancelar</button>
            <button type="button" class="glass-btn-sm btn-cyan" id="sentinelSudoSubmit">Autenticar</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('sentinelSudoSubmit').addEventListener('click', () => this.submitSudoPassword());
    document.getElementById('sentinelSudoInput').addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        this.submitSudoPassword();
      }
    });
  },

  showSudoModal(message) {
    const desc = document.getElementById('sentinelSudoDesc');
    const error = document.getElementById('sentinelSudoError');
    const input = document.getElementById('sentinelSudoInput');
    desc.innerHTML = this.renderMarkdown(message || 'Introduce la contrasena sudo para continuar.');
    error.classList.add('d-none');
    input.value = '';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('sentinelSudoModal')).show();
    setTimeout(() => input.focus(), 150);
  },

  hideSudoModal() {
    const modal = document.getElementById('sentinelSudoModal');
    if (modal) bootstrap.Modal.getOrCreateInstance(modal).hide();
  },

  renderMarkdown(text) {
    return this.escapeHtml(text)
      .replace(/^### (.+)$/gm, '<h5 class="text-cyan mt-2">$1</h5>')
      .replace(/^## (.+)$/gm, '<h4 class="text-cyan mt-2">$1</h4>')
      .replace(/^# (.+)$/gm, '<h4 class="text-cyan mt-2">$1</h4>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^---$/gm, '<hr>')
      .replace(/\n/g, '<br>');
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};

document.addEventListener('DOMContentLoaded', () => sentinel.init());
