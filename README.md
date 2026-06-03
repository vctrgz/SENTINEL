# SentinelAI
AI Agents Workflow for Cybersecurity purposes
# 🛡️ SentinelAI - Guía de Instalación 

Este documento detalla los pasos necesarios para configurar el entorno de SentinelAI en los principales sistemas operativos.

---

## 🪟 Instalación en WINDOWS

### 1. Instalación de Python 3.12

Elige el método que prefieras:

**🔹 Vía Terminal (PowerShell como Administrador):**

```powershell
winget install -e --id Python.Python.3.12
```

**🔹 Vía Instalador Web:**

1. Descarga el instalador desde: https://www.python.org/
2. ⚠️ **IMPORTANTE:** Marca la casilla **"Add Python to PATH"** antes de instalar.

**🔹 Vía Microsoft Store:**

1. Abre microsoft store y busca la aplicación pyhton 3.12.
2. Instala la aplicación.

---

### 2. Configuración de Ollama

1. Descarga el instalador desde: https://ollama.com/
2. Ejecuta en PowerShell (Administrador):

```powershell
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0', 'User')
```

3. Reinicia Ollama (cerrar desde bandeja y abrir de nuevo)

4. Descarga el modelo:

```powershell
ollama pull foundation-sec
```

---

### 3. Instalación de Librerías

```powershell
python -m pip install fastapi==0.135.3 uvicorn==0.44.0 pydantic==2.12.5 langchain==0.1.20 langchain-community==0.0.38 langchainhub==0.1.21 python-dotenv==1.2.2
```

---

### 4. Ejecución del Servidor

```powershell
cd Sentinel
python run.py
```

Alternativa directa con Uvicorn:

```powershell
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🍎 Instalación en macOS

### 1. Instalación de Python 3.12

**🔹 Con Homebrew:**

```bash
brew install python@3.12
```

**🔹 Vía Instalador Web:**
Descarga el paquete desde: https://www.python.org/

---

### 2. Configuración de Ollama

1. Descarga desde: https://ollama.com/

2. Mueve la app a **Aplicaciones** y ejecútala

3. Configura el host:

```bash
launchctl setenv OLLAMA_HOST "0.0.0.0"
```

4. Reinicia Ollama

5. Descarga el modelo:

```bash
ollama pull foundation-sec
```

---

### 3. Instalación de Librerías

```bash
pip3 install fastapi "uvicorn[standard]" langchain langchain-ollama langchain-community pydantic httpx watchfiles
```

---

### 4. Ejecución del Servidor

```bash
cd Sentinel
python3 run.py
```

Alternativa directa con Uvicorn:

```bash
python3 -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🐧 Instalación en LINUX (Ubuntu / Debian / Parrot)

### 1. Instalación de Python 3.12

```bash
sudo apt update
sudo apt install python3.12 python3-pip -y
```

---

### 2. Configuración de Ollama

**Instalación:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Configurar acceso de red:**

```bash
sudo systemctl edit ollama.service
```

Añadir:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

**Aplicar cambios:**

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Descargar modelo:**

```bash
ollama pull foundation-sec
```

---

### 3. Instalación de Librerías

```bash
pip3 install fastapi==0.135.3 uvicorn==0.44.0 pydantic==2.12.5 langchain==0.1.20 langchain-community==0.0.38 langchainhub==0.1.21 python-dotenv==1.2.2
```

---

### 4. Ejecución del Servidor

```bash
cd Sentinel
python3 run.py
```

Alternativa directa con Uvicorn:

```bash
python3 -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

---
## 🚀 Uso y Verificación

Una vez que el servidor esté corriendo, puedes interactuar con SentinelAI de la siguiente manera:

---

### 🔹 Documentación Interactiva (Swagger)

Accede desde tu navegador:

```id="x2h9kp"
http://localhost:8000/docs
```

Permite probar los endpoints directamente.

---

### 🔹 Estado de Ollama

Verifica que Ollama está funcionando:

```id="m7q4zs"
http://localhost:11434
```

---

### 🔹 Cierre del servidor

Para detener el proceso, usa en la terminal:

```id="p9t1an"
Ctrl + C
```
