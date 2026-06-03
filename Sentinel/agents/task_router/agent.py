import shlex
from agents.executors.shell_executor import ShellExecutor
from sandbox.sandbox_executor import SandboxExecutor
from agents.executors.tool_manager import ToolManager
from app.config import Config
from utils.logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# Command category sets
# ─────────────────────────────────────────────────────────────────────────────

PACKAGE_MANAGERS  = {"apt", "apt-get", "pip", "pip3", "npm", "yarn", "cargo", "gem", "go"}
SYSTEM_COMMANDS   = {"systemctl", "service", "mount", "umount", "fdisk", "mkfs", "iptables", "ufw"}
SAFE_READ_COMMANDS = {
    "ls", "cat", "head", "tail", "grep", "find", "wc", "echo",
    "pwd", "whoami", "date", "which", "file", "ip", "ifconfig",
    "arp", "ss", "netstat", "route", "ipconfig"
}

# Network recon tools — run via shell (they need real network access)
# These are NOT sandboxed because the sandbox has --network=none
NETWORK_RECON_COMMANDS = {
    "nmap", "masscan", "arp-scan", "netdiscover", "fping",
    "nc", "netcat", "curl", "wget", "ping", "traceroute",
    "dig", "nslookup", "host", "whois", "tracert"
}

# Network admin commands (need system access, not just recon)
NETWORK_ADMIN_COMMANDS = {"ssh", "scp", "ftp", "sftp", "telnet"}


class TaskRouter:
    """
    Semantic command router. Classifies each command and dispatches to the
    correct executor.

    IMPORTANT for network recon:
    - nmap, arp-scan, masscan → ShellExecutor (needs real network)
    - SandboxExecutor has --network=none, so it CANNOT do network recon
    - System-critical commands → SandboxExecutor (isolation required)
    """

    def __init__(self):
        self.shell_executor   = ShellExecutor()
        self.sandbox_executor = SandboxExecutor()
        self.tool_manager     = ToolManager()

        # Default executor based on sandbox mode
        # Note: network recon always overrides to shell, regardless of sandbox mode
        self._default_executor = (
            self.sandbox_executor if Config.SANDBOX_MODE
            else self.shell_executor
        )

        logger.info(
            f"[TaskRouter] Default executor: "
            f"{'SandboxExecutor' if Config.SANDBOX_MODE else 'ShellExecutor'} "
            f"(network recon always uses ShellExecutor)"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def route(self, commands: list) -> list:
        routed = []
        for cmd_obj in commands:
            cmd = cmd_obj.get("cmd", "") if isinstance(cmd_obj, dict) else str(cmd_obj)
            category, executor_name = self._classify(cmd)
            routed.append({
                "cmd":      cmd,
                "category": category,
                "executor": executor_name,
                "risk":     cmd_obj.get("risk", "medium") if isinstance(cmd_obj, dict) else "medium"
            })
            logger.debug(f"[TaskRouter] {category:16} → {executor_name:16} | {cmd[:60]}")
        return routed

    def execute(self, commands: list) -> list:
        results = []
        for item in self.route(commands):
            results.append(self._dispatch(item))
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Classification
    # ─────────────────────────────────────────────────────────────────────────

    def _classify(self, cmd: str) -> tuple[str, str]:
        if not cmd or not cmd.strip():
            return "empty", "shell"

        try:
            parts    = shlex.split(cmd)
            base_cmd = parts[0] if parts else ""
        except ValueError:
            base_cmd = cmd.split()[0] if cmd.split() else ""

        # Strip sudo to get the actual command
        effective = base_cmd
        if base_cmd == "sudo" and len(cmd.split()) > 1:
            effective = cmd.split()[1]

        # 1. Package managers → ToolManager
        if effective in PACKAGE_MANAGERS:
            return "package", "tool_manager"

        # 2. Network RECON → ShellExecutor (MUST have network access)
        #    This is the critical fix: nmap cannot run in --network=none sandbox
        if effective in NETWORK_RECON_COMMANDS:
            return "network_recon", "shell"

        # 3. Network admin (ssh, scp) → shell (needs real network)
        if effective in NETWORK_ADMIN_COMMANDS:
            return "network_admin", "shell"

        # 4. System-critical → sandbox (isolation required)
        if effective in SYSTEM_COMMANDS:
            return "system", "sandbox"

        # 5. Safe read-only → shell (no need for sandbox overhead)
        if effective in SAFE_READ_COMMANDS:
            return "safe_read", "shell"

        # 6. Scripts
        if effective in {"python", "python3", "node", "ruby", "perl"}:
            return "script", "sandbox"

        # 7. VCS
        if effective == "git":
            return "vcs", "shell"

        # 8. Docker
        if effective == "docker":
            return "container", "shell"

        # 9. Compilers/builds
        if effective in {"gcc", "g++", "make", "cmake", "cargo", "mvn", "gradle"}:
            return "build", "sandbox"

        # Default
        return "general", ("sandbox" if Config.SANDBOX_MODE else "shell")

    # ─────────────────────────────────────────────────────────────────────────
    # Dispatch
    # ─────────────────────────────────────────────────────────────────────────

    def _dispatch(self, item: dict) -> dict:
        executor_name = item["executor"]
        cmd           = item["cmd"]

        if executor_name == "tool_manager":
            parts = cmd.split()
            tool  = parts[-1] if parts else cmd
            return self.tool_manager.ensure_tool(tool)

        elif executor_name == "sandbox":
            return self.sandbox_executor.execute(cmd)

        else:  # "shell" — covers both safe_read and network_recon
            return self.shell_executor.execute(cmd)
