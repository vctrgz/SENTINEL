"""
utils/sudo_manager.py

Thread-safe singleton that coordinates sudo password collection between:
  - Executor threads   (ShellExecutor blocks here while waiting for password)
  - The SSE generator  (polls is_waiting_for_password() to know when to ask)
  - The /sudo-auth endpoint  (calls set_password() when user submits)

Flow:
  1. ShellExecutor sees "sudo" command → calls request_password()
  2. request_password() sets _requesting flag, then blocks on _password_event
  3. SSE generator detects _requesting flag → emits "needs_sudo" to browser
  4. User types password in modal → browser POSTs to /sudo-auth
  5. /sudo-auth calls set_password() → _password_event fires, unblocking step 2
  6. ShellExecutor retries the command with sudo -S and piped password
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from typing import Optional

from utils.logger import logger


class SudoManager:
    """Session-scoped sudo password manager (singleton)."""

    _instance: Optional["SudoManager"] = None
    _init_lock = threading.Lock()

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._password: Optional[str] = None
        self._password_event = threading.Event()   # fires when password is set
        self._requesting     = threading.Event()   # set while waiting for password
        self._needs_pw: Optional[bool] = None      # cached sudo-n result
        self._rw_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SudoManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── System checks ────────────────────────────────────────────────────

    def sudo_binary_available(self) -> bool:
        """True if sudo exists in PATH."""
        return shutil.which("sudo") is not None

    def sudo_needs_password(self) -> bool:
        """
        Returns True when sudo requires a password on this machine.
        Result is cached after the first call.
        """
        if self._needs_pw is not None:
            return self._needs_pw
        if not self.sudo_binary_available():
            self._needs_pw = False
            return False
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=4,
            )
            self._needs_pw = result.returncode != 0
        except FileNotFoundError:
            self._needs_pw = False
        except Exception:
            self._needs_pw = True   # be safe: assume password needed
        logger.info(f"[SudoManager] sudo_needs_password={self._needs_pw}")
        return self._needs_pw

    # ── Password state ───────────────────────────────────────────────────

    def has_password(self) -> bool:
        return self._password is not None

    def get_password(self) -> Optional[str]:
        return self._password

    def set_password(self, password: str) -> None:
        """Called by the /sudo-auth endpoint when the user submits a password."""
        with self._rw_lock:
            self._password = password
            self._password_event.set()
        logger.info("[SudoManager] Password received and cached")

    def clear_password(self) -> None:
        """Clear cached password (e.g. after wrong-password detection)."""
        with self._rw_lock:
            self._password = None
            self._password_event.clear()
        logger.info("[SudoManager] Cached password cleared")

    # ── Blocking request (called from executor thread) ────────────────────

    def is_waiting_for_password(self) -> bool:
        """
        True while an executor thread is blocked inside request_password().
        Polled by the SSE generator every 2 s to decide when to emit
        the 'needs_sudo' event.
        """
        return self._requesting.is_set()

    def request_password(self, timeout: float = 180.0) -> bool:
        """
        Block the calling thread until the user provides a sudo password
        (or the timeout expires).

        Returns True on success, False on timeout.
        """
        # Already have it — no need to block
        if self.has_password():
            return True

        logger.info("[SudoManager] Waiting for sudo password from user…")
        self._password_event.clear()
        self._requesting.set()          # ← SSE loop will now emit needs_sudo

        got = self._password_event.wait(timeout=timeout)

        self._requesting.clear()        # ← SSE loop stops repeating the prompt
        if not got:
            logger.warning("[SudoManager] Timeout: user did not provide sudo password")
        return got

    # ── Command helpers ──────────────────────────────────────────────────

    def stdin_payload(self) -> str:
        """Return the string to pipe into sudo -S (password + newline)."""
        return (self._password or "") + "\n"

    @staticmethod
    def inject_sudo_s(cmd: str) -> str:
        """
        Rewrite 'sudo [flags] <rest>' → 'sudo -S [flags] <rest>'
        so that sudo reads the password from stdin.
        Idempotent: already-present -S or -n flags are preserved.
        """
        # Strip leading whitespace
        stripped = cmd.lstrip()
        if not stripped.startswith("sudo"):
            return cmd

        after_sudo = stripped[4:]           # everything after 'sudo'
        # Extract any existing short flags (e.g.  -n  -k  -S  -v)
        flag_match = re.match(r"(\s+-[a-zA-Z]+)*\s+", after_sudo)
        flags_str  = flag_match.group(0) if flag_match else " "
        flags      = set(re.findall(r"-([a-zA-Z]+)", flags_str))

        # Remove -n (non-interactive) since we're providing -S
        flags.discard("n")
        flags.add("S")

        rest_start = len(flags_str) if flag_match else 1
        rest       = after_sudo[rest_start:]

        new_flags  = " ".join(f"-{f}" for f in sorted(flags))
        return f"sudo {new_flags} {rest}"

    @staticmethod
    def clean_sudo_stderr(stderr: str) -> str:
        """Strip '[sudo] password for …' prompt lines from stderr."""
        cleaned = []
        for line in stderr.splitlines():
            lower = line.lower()
            if re.match(r"^\[sudo\]", line) or "password for" in lower:
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def is_wrong_password_error(stderr: str) -> bool:
        lower = stderr.lower()
        return (
            "incorrect password attempt" in lower
            or "sorry, try again" in lower
            or "authentication failure" in lower
        )

    @staticmethod
    def is_unsupported_stdin_flag_error(stderr: str) -> bool:
        lower = stderr.lower()
        return (
            "unexpected argument '-s' found" in lower
            or "unknown option -- s" in lower
            or "invalid option -- 's'" in lower
        )
