import re
import shlex
from dataclasses import dataclass
from typing import List, Optional
from utils.logger import logger


# ------------------------------------------------------------------ #
# Patrones peligrosos — con variantes                                  #
# ------------------------------------------------------------------ #

@dataclass
class DangerPattern:
    name:        str
    description: str
    patterns:    List[str]   # expresiones regulares
    risk:        str         # "critical" | "high" | "medium"
    blockable:   bool = True # False = solo warn, no bloquear


DANGER_PATTERNS = [
    DangerPattern(
        name="recursive_delete_root",
        description="Eliminación recursiva desde la raíz",
        risk="critical",
        patterns=[
            r"\brm\b.{0,30}\s/\s*$",       # rm -rf /
            r"\brm\b.{0,30}--recursive.{0,20}/",
            r"\brm\b.{0,30}-[a-zA-Z]*r[a-zA-Z]*\s+/",   # rm -rf /, rm -fr /, rm -Rf /
            r"\brm\b.{0,30}-[a-zA-Z]*f[a-zA-Z]*\s+/",
        ]
    ),
    DangerPattern(
        name="fork_bomb",
        description="Fork bomb (consume todos los recursos del sistema)",
        risk="critical",
        patterns=[
            r":\(\)\s*\{",           # :() { :|:& };:
            r"\bfork\s*bomb\b",
        ]
    ),
    DangerPattern(
        name="disk_wipe",
        description="Escritura directa a dispositivo de bloques",
        risk="critical",
        patterns=[
            r"\bdd\b.{0,40}of=/dev/[sh]d",  # dd if=... of=/dev/sda
            r"\bdd\b.{0,40}of=/dev/nvme",
            r"\bmkfs\b",                     # formatear sistema de archivos
            r"\bwipefs\b",
        ]
    ),
    DangerPattern(
        name="shutdown_reboot",
        description="Apagado o reinicio del sistema",
        risk="critical",
        patterns=[
            r"\bshutdown\b",
            r"\breboot\b",
            r"\bpoweroff\b",
            r"\bhalt\b",
            r"\binit\s+[06]\b",
        ]
    ),
    DangerPattern(
        name="chmod_world_writable",
        description="Permisos de escritura global (777) en directorios raíz",
        risk="high",
        patterns=[
            r"\bchmod\b.{0,20}777.{0,20}/\s",
            r"\bchmod\b.{0,20}-R.{0,20}777",
            r"\bchmod\b.{0,20}0777",
        ]
    ),
    DangerPattern(
        name="iptables_disable",
        description="Desactivación del firewall",
        risk="high",
        patterns=[
            r"\bufw\s+disable\b",
            r"\biptables\s+-F\b",    # flush all rules
            r"\biptables\s+--flush\b",
        ]
    ),
    DangerPattern(
        name="crontab_wipe",
        description="Borrado de tareas programadas",
        risk="high",
        patterns=[
            r"\bcrontab\s+-r\b",
        ]
    ),
    DangerPattern(
        name="dev_null_redirect",
        description="Redireccionamiento a /dev/null de archivos del sistema",
        risk="high",
        patterns=[
            r">\s*/etc/(?:passwd|shadow|hosts|sudoers)",
            r">\s*/boot/",
        ]
    ),
]


# ------------------------------------------------------------------ #
# Resultado                                                            #
# ------------------------------------------------------------------ #

@dataclass
class CommandValidationResult:
    valid:           bool
    reason:          str
    risk:            str      = "low"    # "low" | "medium" | "high" | "critical"
    pattern_matched: Optional[str] = None
    normalized_cmd:  str      = ""


# ------------------------------------------------------------------ #
# CommandValidator semántico                                           #
# ------------------------------------------------------------------ #

class CommandValidator:
    """
    Alerta #8: el validador original solo bloqueaba 5 patrones literales.
    Era trivialmente bypasseable con variantes como:
    - 'rm -r -f /' en lugar de 'rm -rf /'
    - 'rm --recursive /'
    - uso de aliases o variables de shell

    El nuevo validador:
    1. Normaliza el comando antes de analizarlo
    2. Usa expresiones regulares que capturan variantes
    3. Detecta el uso de sudo para escalar el nivel de riesgo
    4. Clasifica en niveles de riesgo en lugar de bloqueo binario
    """

    def __init__(self):
        self._compiled = [
            (dp, [re.compile(p, re.IGNORECASE) for p in dp.patterns])
            for dp in DANGER_PATTERNS
        ]

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def validate(self, cmd: str) -> CommandValidationResult:
        """
        Valida un comando y devuelve el resultado con nivel de riesgo.
        """
        if not cmd or not cmd.strip():
            return CommandValidationResult(
                valid=False, reason="Comando vacío", risk="low", normalized_cmd=""
            )

        # 1. Normalizar antes de validar (clave para evitar bypass)
        normalized = self._normalize(cmd)

        # 2. Verificar sintaxis básica
        try:
            parts = shlex.split(normalized)
        except ValueError as e:
            return CommandValidationResult(
                valid=False, reason=f"Sintaxis inválida: {e}",
                risk="medium", normalized_cmd=normalized
            )

        if not parts:
            return CommandValidationResult(
                valid=False, reason="Comando vacío tras normalización",
                risk="low", normalized_cmd=normalized
            )

        # 3. Detectar sudo (escala el riesgo)
        has_sudo = parts[0] == "sudo"

        # 4. Comprobar patrones de peligro
        for danger, regexes in self._compiled:
            for regex in regexes:
                if regex.search(normalized):
                    risk = "critical" if has_sudo else danger.risk

                    logger.warning(
                        f"[CommandValidator] Patrón peligroso '{danger.name}' "
                        f"en: {cmd[:80]}"
                    )

                    return CommandValidationResult(
                        valid=False if danger.blockable else True,
                        reason=(
                            f"Comando bloqueado: {danger.description} "
                            f"(patrón: {danger.name})"
                        ),
                        risk=risk,
                        pattern_matched=danger.name,
                        normalized_cmd=normalized
                    )

        # 5. Clasificar riesgo residual
        risk = self._assess_residual_risk(parts, has_sudo)

        return CommandValidationResult(
            valid=True,
            reason="ok",
            risk=risk,
            normalized_cmd=normalized
        )

    def validate_batch(self, commands: List[str]) -> List[CommandValidationResult]:
        """Valida una lista de comandos."""
        return [self.validate(cmd) for cmd in commands]

    def is_safe(self, cmd: str) -> bool:
        """Shortcut: devuelve True solo si el comando es válido y de riesgo bajo/medio."""
        result = self.validate(cmd)
        return result.valid and result.risk in ("low", "medium")

    # ------------------------------------------------------------------ #
    # Normalización — la clave para evitar bypasses                        #
    # ------------------------------------------------------------------ #

    def _normalize(self, cmd: str) -> str:
        """
        Normaliza el comando para que los patrones de detección sean robustos:
        - Elimina espacios extra
        - Expande flags compactos comprobando argumentos de rm, chmod, etc.
        - Elimina comillas redundantes alrededor de la ruta raíz
        """
        normalized = cmd.strip()

        # Normalizar espacios múltiples
        normalized = re.sub(r'\s+', ' ', normalized)

        # Eliminar comillas alrededor de / (rm -rf "/")
        normalized = re.sub(r'["\']/?["\']', '/', normalized)

        # Expandir flags compactos de rm: -rf → -r -f (para facilitar regex)
        # Esto hace que 'rm -rf' y 'rm -fr' y 'rm -r -f' sean equivalentes
        normalized = re.sub(
            r'\brm\s+(-[a-zA-Z]{2,})',
            lambda m: 'rm ' + ' '.join(f'-{c}' for c in m.group(1)[1:]),
            normalized
        )

        return normalized

    def _assess_residual_risk(self, parts: List[str], has_sudo: bool) -> str:
        """Clasifica el riesgo residual de comandos que no activan patrones críticos."""
        if not parts:
            return "low"

        base = parts[0] if parts[0] != "sudo" else (parts[1] if len(parts) > 1 else "")

        # Comandos de solo lectura → bajo riesgo
        safe_read = {"ls", "cat", "head", "tail", "grep", "find", "wc", "echo",
                     "pwd", "whoami", "date", "which", "file", "stat", "env",
                     "dir", "ipconfig", "arp", "route", "netstat"}
        if base in safe_read:
            return "low"

        # Comandos de red o instalación → medio
        medium = {"curl", "wget", "apt", "apt-get", "pip", "pip3", "npm",
                  "git", "docker", "systemctl", "winget", "choco", "brew", "nmap"}
        if base in medium:
            return "high" if has_sudo else "medium"

        # Con sudo siempre sube un nivel
        return "high" if has_sudo else "medium"
