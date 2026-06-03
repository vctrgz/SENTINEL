from __future__ import annotations

import os
import platform


def detect_os_family() -> str:
    system = platform.system().lower()
    if "android" in system or os.environ.get("ANDROID_ROOT") or os.environ.get("TERMUX_VERSION"):
        return "android"
    if "windows" in system:
        return "windows"
    if "freebsd" in system:
        return "freebsd"
    if "darwin" in system or "mac" in system:
        return "macos"
    return "linux"


OS_FAMILY = detect_os_family()
IS_WINDOWS = OS_FAMILY == "windows"
IS_LINUX = OS_FAMILY == "linux"
IS_MACOS = OS_FAMILY == "macos"

OS_ALIASES = {
    "windows": ["windows", "win", "powershell", "cmd", "microsoft"],
    "linux": ["linux", "ubuntu", "debian", "kali", "fedora", "arch", "posix"],
    "macos": ["mac", "macos", "osx", "darwin", "apple"],
    "freebsd": ["freebsd", "bsd", "unix"],
    "android": ["android", "termux", "mobile"],
}

SUPPORTED_OS_FAMILIES = ("windows", "linux", "macos", "freebsd", "android")

CRITICAL_COMMAND_PATTERNS = [
    "rm -rf",
    "shutdown",
    "reboot",
    "mkfs",
    "dd ",
    ":(){ :|:& };:",
    "chmod 777",
    "chown",
    "iptables",
    "ufw disable",
]

SENSITIVE_COMMANDS = [
    "apt install",
    "apt-get install",
    "pip install",
    "npm install",
    "git clone",
    "docker",
    "systemctl",
    "brew install",
    "winget install",
    "choco install",
]

SAFE_COMMANDS = [
    "ls",
    "pwd",
    "echo",
    "cat",
    "whoami",
    "date",
    "dir",
    "ipconfig",
    "arp -a",
]

OS_COMMANDS = {
    "linux": {
        "cidr_detection": ["ip route show", "ip addr show", "ifconfig", "arp -a"],
        "arp_table": "arp -a",
        "nmap_discovery": "sudo nmap -sn {cidr} --host-timeout 10s",
        "nmap_scan": "sudo nmap -sV -sC -O -T4 --open {ip}",
        "python_bin": "venv/bin/python",
        "package_managers": ["apt-get", "apt", "dnf", "yum", "pacman", "zypper", "apk"],
        "shell_family": "posix",
    },
    "macos": {
        "cidr_detection": ["route -n get default", "ifconfig", "arp -a"],
        "arp_table": "arp -a",
        "nmap_discovery": "sudo nmap -sn {cidr} --host-timeout 10s",
        "nmap_scan": "sudo nmap -sV -sC -O -T4 --open {ip}",
        "python_bin": "venv/bin/python",
        "package_managers": ["brew", "port"],
        "shell_family": "posix",
    },
    "freebsd": {
        "cidr_detection": ["netstat -rn", "ifconfig", "arp -a"],
        "arp_table": "arp -a",
        "nmap_discovery": "sudo nmap -sn {cidr} --host-timeout 10s",
        "nmap_scan": "sudo nmap -sV -sC -O -T4 --open {ip}",
        "python_bin": "venv/bin/python",
        "package_managers": ["pkg"],
        "shell_family": "posix",
    },
    "android": {
        "cidr_detection": ["ip route show", "ip addr show", "ifconfig", "arp -a"],
        "arp_table": "arp -a",
        "nmap_discovery": "nmap -sn {cidr} --host-timeout 10s",
        "nmap_scan": "nmap -sV -sC -O -T4 --open {ip}",
        "python_bin": "venv/bin/python",
        "package_managers": ["pkg", "apt"],
        "shell_family": "posix",
    },
    "windows": {
        "cidr_detection": ["ipconfig", "route print", "arp -a"],
        "arp_table": "arp -a",
        "nmap_discovery": "nmap -sn {cidr} --host-timeout 10s",
        "nmap_scan": "nmap -sV -sC -O -T4 --open {ip}",
        "python_bin": "venv\\Scripts\\python.exe",
        "package_managers": ["winget", "choco", "scoop"],
        "shell_family": "windows",
    },
}

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial"
STATUS_FATAL = "fatal"
STATUS_RETRY = "retry"
