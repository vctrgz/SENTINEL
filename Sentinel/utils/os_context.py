from __future__ import annotations

import ipaddress
import os
import platform
import re
import shutil
import sys
from pathlib import Path

from app.constants import OS_COMMANDS

_SHELL_OP_RE = re.compile(r"\|\||&&|[|><`]|<\(|\$\(")
_WINDOWS_CMD_BUILTINS = {
    "assoc", "break", "cd", "chdir", "cls", "copy", "date", "del", "dir",
    "echo", "erase", "for", "ftype", "md", "mkdir", "mklink", "move", "path",
    "pause", "popd", "prompt", "pushd", "rd", "ren", "rename", "rmdir",
    "set", "start", "time", "title", "type", "ver", "vol", "where",
}


def detect_os_context() -> dict:
    system = platform.system()
    normalized = system.lower()
    if "android" in normalized or os.environ.get("ANDROID_ROOT") or os.environ.get("TERMUX_VERSION"):
        family = "android"
    elif "windows" in normalized:
        family = "windows"
    elif "freebsd" in normalized:
        family = "freebsd"
    elif "darwin" in normalized or "mac" in normalized:
        family = "macos"
    else:
        family = "linux"

    shell_executable, shell_kind = detect_default_shell(family=family)
    package_manager = detect_package_manager(family=family)
    return {
        "family": family,
        "system": system,
        "release": platform.release(),
        "version": platform.version(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "shell": shell_executable,
        "shell_kind": shell_kind,
        "package_manager": package_manager,
        "is_windows": family == "windows",
        "is_linux": family == "linux",
        "is_macos": family == "macos",
        "is_freebsd": family == "freebsd",
        "is_android": family == "android",
    }


def build_os_context_block(context: dict | None = None) -> str:
    ctx = context or detect_os_context()
    return (
        "Runtime OS Context:\n"
        f"- OS family: {ctx.get('family', '')}\n"
        f"- System: {ctx.get('system', '')}\n"
        f"- Release: {ctx.get('release', '')}\n"
        f"- Shell: {ctx.get('shell', '')}\n"
        f"- Shell kind: {ctx.get('shell_kind', '')}\n"
        f"- Package manager: {ctx.get('package_manager', 'unknown')}\n"
        f"- Python executable: {ctx.get('python_executable', '')}"
    )


def get_os_commands(context: dict | None = None) -> dict:
    ctx = context or detect_os_context()
    return OS_COMMANDS.get(ctx["family"], OS_COMMANDS["linux"])


def build_discovery_command(cidr: str, context: dict | None = None) -> str:
    return get_os_commands(context)["nmap_discovery"].format(cidr=cidr)


def build_host_scan_command(ip: str, context: dict | None = None) -> str:
    return get_os_commands(context)["nmap_scan"].format(ip=ip)


def get_arp_command(context: dict | None = None) -> str:
    return get_os_commands(context)["arp_table"]


def iter_cidr_detection_commands(context: dict | None = None) -> list[str]:
    return list(get_os_commands(context)["cidr_detection"])


def parse_windows_cidr(ipconfig_output: str) -> str | None:
    ipv4_match = re.search(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", ipconfig_output, re.IGNORECASE)
    mask_match = re.search(r"Subnet Mask[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", ipconfig_output, re.IGNORECASE)
    if not ipv4_match or not mask_match:
        return None
    try:
        network = ipaddress.ip_network(
            f"{ipv4_match.group(1)}/{mask_match.group(1)}",
            strict=False,
        )
        return str(network)
    except Exception:
        return None


def likely_windows_store_stub(path: str) -> bool:
    normalized = (path or "").lower()
    return "windowsapps" in normalized and "pythonsoftwarefoundation.python" in normalized


def candidate_host_python_commands() -> list[list[str]]:
    candidates: list[list[str]] = []

    if shutil.which("python3"):
        candidates.append(["python3"])
    if shutil.which("python"):
        candidates.append(["python"])
    if shutil.which("py"):
        candidates.append(["py", "-3"])
        candidates.append(["py"])

    exe = sys.executable
    if exe:
        candidates.insert(0, [exe])

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for item in candidates:
        key = tuple(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def detect_default_shell(family: str | None = None) -> tuple[str, str]:
    family = family or detect_os_context()["family"]

    if family == "windows":
        for shell in (
            os.environ.get("POWERSHELL"),
            shutil.which("pwsh"),
            shutil.which("powershell"),
            os.environ.get("COMSPEC"),
        ):
            if shell:
                shell_lower = str(shell).lower()
                kind = "powershell" if "pwsh" in shell_lower or "powershell" in shell_lower else "cmd"
                return str(shell), kind
        return "cmd.exe", "cmd"

    shell = os.environ.get("SHELL") or shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    return shell, "posix"


def detect_package_manager(family: str | None = None) -> str | None:
    family = family or detect_os_context()["family"]
    candidates = get_os_commands({"family": family}).get("package_managers", [])
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return None


def split_command(command: str, context: dict | None = None) -> list[str]:
    import shlex

    ctx = context or detect_os_context()
    return shlex.split(command, posix=not ctx["is_windows"])


def command_base(command: str, context: dict | None = None) -> str:
    try:
        parts = split_command(command, context)
    except ValueError:
        return ""
    return parts[0].lower() if parts else ""


def is_powershell_command(command: str, context: dict | None = None) -> bool:
    ctx = context or detect_os_context()
    if not ctx["is_windows"]:
        return False

    base = command_base(command, ctx)
    if not base:
        return False

    if "-" in base and re.match(r"^[a-z]+-[a-z0-9]+$", base, re.IGNORECASE):
        return True

    ps_markers = ("$env:", "$PSVersionTable", "Select-String", "Get-", "Set-", "New-", "Remove-")
    return any(marker.lower() in command.lower() for marker in ps_markers)


def is_shell_builtin(command: str, context: dict | None = None) -> bool:
    ctx = context or detect_os_context()
    base = command_base(command, ctx)
    if not base:
        return False
    if ctx["is_windows"]:
        return base in _WINDOWS_CMD_BUILTINS or is_powershell_command(command, ctx)
    return False


def needs_native_shell(command: str, context: dict | None = None) -> bool:
    ctx = context or detect_os_context()
    return bool(_SHELL_OP_RE.search(command)) or is_shell_builtin(command, ctx)


def build_shell_command(command: str, context: dict | None = None) -> list[str]:
    ctx = context or detect_os_context()
    shell_executable, shell_kind = detect_default_shell(ctx["family"])

    if ctx["is_windows"]:
        if is_powershell_command(command, ctx):
            powershell = shell_executable
            if shell_kind != "powershell":
                powershell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            return [powershell, "-NoProfile", "-NonInteractive", "-Command", command]

        cmd_shell = os.environ.get("COMSPEC") or shutil.which("cmd") or "cmd.exe"
        return [cmd_shell, "/d", "/s", "/c", command]

    return [shell_executable, "-lc", command]


def build_install_command(tool_name: str, context: dict | None = None) -> list[str] | None:
    ctx = context or detect_os_context()
    manager = ctx.get("package_manager") or detect_package_manager(ctx["family"])
    if not manager:
        return None

    sudo = ["sudo"] if ctx["family"] in {"linux", "macos", "freebsd"} and shutil.which("sudo") else []
    commands = {
        "apt-get": sudo + ["apt-get", "install", "-y", tool_name],
        "apt": sudo + ["apt", "install", "-y", tool_name],
        "apk": ["apk", "add", "--no-cache", tool_name],
        "dnf": sudo + ["dnf", "install", "-y", tool_name],
        "yum": sudo + ["yum", "install", "-y", tool_name],
        "pacman": sudo + ["pacman", "-S", "--noconfirm", tool_name],
        "zypper": sudo + ["zypper", "install", "-y", tool_name],
        "brew": ["brew", "install", tool_name],
        "port": sudo + ["port", "install", tool_name],
        "pkg": ["pkg", "install", "-y", tool_name],
        "winget": ["winget", "install", "--exact", "--id", tool_name],
        "choco": ["choco", "install", tool_name, "-y"],
        "scoop": ["scoop", "install", tool_name],
    }
    return commands.get(manager)


def build_install_hint(tool_name: str, context: dict | None = None) -> str:
    cmd = build_install_command(tool_name, context)
    return " ".join(cmd) if cmd else f"install {tool_name} manually for this operating system"
