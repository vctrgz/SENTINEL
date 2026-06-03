"""
utils/runtime_tracer.py

Sistema de trazabilidad en tiempo real para SentinelAI.

Emite cada acción a:
  1. stdout  — con colores ANSI y timestamps (visible en la terminal/servidor)
  2. logs/runtime.log — archivo rotante en formato JSONL
  3. logs/runtime_human.log — formato legible para humanos (como sysout)

Qué se traza:
  - Cada agente que se llama (orchestrator, planner, translator, etc.)
  - Cada skill .md que se carga (prompt_loader → skill_loader)
  - Cada comando que se ejecuta (shell/sandbox/tool_manager)
  - Cada llamada al LLM (Ollama) con modelo y duración
  - Cada fase del bucle ReAct (reason/act/observe)
  - Cada resultado de red (hosts descubiertos, puertos)

Uso:
    from utils.runtime_tracer import get_tracer
    tracer = get_tracer()
    tracer.log("planner", "plan_generated", {"task_count": 3})
    tracer.log_skill_load("network_recon", "/path/to/SKILL.md")
    tracer.log_command("nmap -sn 192.168.1.0/24", "shell", returncode=0)
    tracer.log_llm_call("qwen2.5:latest", duration_s=2.3, tokens_est=400)
"""

import json
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# ANSI colours for stdout
# ─────────────────────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

# Agent colours
COLOURS = {
    "orchestrator": "\033[96m",   # bright cyan
    "planner":      "\033[94m",   # bright blue
    "translator":   "\033[93m",   # bright yellow
    "supervisor":   "\033[91m",   # bright red
    "reflector":    "\033[95m",   # bright magenta
    "task_router":  "\033[92m",   # bright green
    "synthesizer":  "\033[36m",   # cyan
    "shell":        "\033[33m",   # yellow
    "sandbox":      "\033[31m",   # red
    "tool_manager": "\033[32m",   # green
    "llm":          "\033[35m",   # magenta
    "skill":        "\033[90m",   # dark grey
    "memory":       "\033[34m",   # blue
    "network":      "\033[92m",   # bright green
    "system":       "\033[37m",   # white
}

ICONS = {
    "orchestrator": "🧠",
    "planner":      "📋",
    "translator":   "🔄",
    "supervisor":   "🛡 ",
    "reflector":    "🔍",
    "task_router":  "🔀",
    "synthesizer":  "📊",
    "shell":        "💻",
    "sandbox":      "📦",
    "tool_manager": "🔧",
    "llm":          "🤖",
    "skill":        "📖",
    "memory":       "🧩",
    "network":      "🌐",
    "system":       "⚙️ ",
}

MAX_LOG_SIZE_MB  = 5
MAX_ROTATED_FILES = 3


# ─────────────────────────────────────────────────────────────────────────────
# RuntimeTracer
# ─────────────────────────────────────────────────────────────────────────────

class RuntimeTracer:
    """
    Thread-safe real-time tracer.
    Writes to stdout AND to rotating log files simultaneously.
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._jsonl_path  = self._log_dir / "runtime.jsonl"
        self._human_path  = self._log_dir / "runtime_human.log"

        # Write session header to human log
        self._write_human(
            f"\n{'='*70}\n"
            f"  SentinelAI Runtime Trace — Session {self._session_id}\n"
            f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*70}\n"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Core log method
    # ─────────────────────────────────────────────────────────────────────────

    def log(
        self,
        agent: str,
        action: str,
        data: Optional[Any] = None,
        *,
        level: str = "INFO",
    ) -> None:
        """
        Log a generic agent action.

        Args:
            agent:  name of the component (e.g. "planner", "shell")
            action: short description of what happened (e.g. "plan_generated")
            data:   optional dict/str with additional context
            level:  "INFO" | "WARN" | "ERROR" | "DEBUG"
        """
        ts     = time.time()
        ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]

        record = {
            "ts":      ts,
            "ts_str":  ts_str,
            "session": self._session_id,
            "level":   level,
            "agent":   agent,
            "action":  action,
        }
        if data is not None:
            record["data"] = data

        # ── stdout ────────────────────────────────────────────────────────────
        colour = COLOURS.get(agent, "\033[37m")
        icon   = ICONS.get(agent, "•")
        data_str = ""
        if data is not None:
            try:
                raw = json.dumps(data, ensure_ascii=False, default=str)
                data_str = f" {DIM}│ {raw[:120]}{'…' if len(raw) > 120 else ''}{RESET}"
            except Exception:
                data_str = f" {DIM}│ {str(data)[:120]}{RESET}"

        level_colour = {
            "ERROR": "\033[91m",
            "WARN":  "\033[93m",
            "DEBUG": "\033[90m",
            "INFO":  "",
        }.get(level, "")

        line = (
            f"{DIM}{ts_str}{RESET}  "
            f"{colour}{BOLD}{icon} [{agent.upper():12}]{RESET}  "
            f"{level_colour}{action}{RESET}"
            f"{data_str}"
        )

        with self._lock:
            try:
                print(line, flush=True)
            except UnicodeEncodeError:
                safe_line = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                    sys.stdout.encoding or "utf-8",
                    errors="replace",
                )
                print(safe_line, flush=True)
            self._append_jsonl(record)
            self._write_human(
                f"{ts_str}  [{level:5}]  [{agent.upper():12}]  {action}"
                + (f"  | {str(data)[:200]}" if data else "")
                + "\n"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Specialised log helpers
    # ─────────────────────────────────────────────────────────────────────────

    def log_skill_load(self, skill_name: str, path: str, agent: str = "system") -> None:
        """Emitted every time a SKILL.md is read from disk."""
        self.log("skill", f"load_skill:{skill_name}", {"path": path, "from_agent": agent})

    def log_agent_md_load(self, agent_name: str, path: str) -> None:
        """Emitted every time an AGENTS.md is read from disk."""
        self.log("skill", f"load_agents_md:{agent_name}", {"path": path})

    def log_command(
        self,
        cmd: str,
        executor: str,
        returncode: int,
        stdout_len: int = 0,
        stderr: str = "",
        duration_s: float = 0.0,
    ) -> None:
        """Emitted for every shell/sandbox/tool_manager command execution."""
        level   = "INFO" if returncode == 0 else "WARN"
        status  = "✓ ok" if returncode == 0 else f"✗ rc={returncode}"
        self.log(
            executor,
            f"exec:{status}  {cmd[:80]}{'…' if len(cmd) > 80 else ''}",
            {
                "returncode": returncode,
                "stdout_bytes": stdout_len,
                "stderr_preview": stderr[:100] if stderr else None,
                "duration_s": round(duration_s, 3),
            },
            level=level,
        )

    def log_llm_call(
        self,
        model: str,
        agent: str = "llm",
        duration_s: float = 0.0,
        tokens_est: int = 0,
        expect_json: bool = False,
    ) -> None:
        """Emitted for every Ollama API call."""
        self.log("llm", f"ollama_call:{model}", {
            "agent":       agent,
            "expect_json": expect_json,
            "duration_s":  round(duration_s, 3),
            "tokens_est":  tokens_est,
        })

    def log_react_phase(self, iteration: int, phase: str, detail: Any = None) -> None:
        """Emitted at each ReAct loop phase: reason | act | observe."""
        icons = {"reason": "🤔", "act": "⚡", "observe": "👁 "}
        self.log("orchestrator", f"{icons.get(phase, '•')} react:{phase}:iter{iteration}", detail)

    def log_network_event(self, event: str, data: Any = None) -> None:
        """Emitted for network discovery milestones."""
        self.log("network", event, data)

    def log_phase(self, phase_name: str, detail: Any = None) -> None:
        """Emitted at the start/end of a named execution phase."""
        self.log("orchestrator", f"phase:{phase_name}", detail)

    def separator(self, label: str = "") -> None:
        """Print a visual separator to stdout and human log."""
        line = f"{'─'*25} {label} {'─'*25}" if label else "─" * 60
        with self._lock:
            print(f"\n{DIM}{line}{RESET}", flush=True)
            self._write_human(f"\n{line}\n")

    # ─────────────────────────────────────────────────────────────────────────
    # File I/O
    # ─────────────────────────────────────────────────────────────────────────

    def _append_jsonl(self, record: dict) -> None:
        self._rotate_if_needed(self._jsonl_path)
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # never crash the main process because of logging

    def _write_human(self, text: str) -> None:
        self._rotate_if_needed(self._human_path)
        try:
            with open(self._human_path, "a", encoding="utf-8") as fh:
                fh.write(text)
        except Exception:
            pass

    def _rotate_if_needed(self, path: Path) -> None:
        try:
            if path.exists() and path.stat().st_size > MAX_LOG_SIZE_MB * 1024 * 1024:
                ts       = int(time.time())
                rotated  = path.with_name(f"{path.stem}_{ts}{path.suffix}")
                path.rename(rotated)
                # Prune old rotated files
                siblings = sorted(path.parent.glob(f"{path.stem}_*{path.suffix}"))
                for old in siblings[:-MAX_ROTATED_FILES]:
                    old.unlink(missing_ok=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_tracer_instance: Optional[RuntimeTracer] = None


def get_tracer() -> RuntimeTracer:
    """Return the process-wide RuntimeTracer singleton."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = RuntimeTracer()
    return _tracer_instance
