"""
network_parser.py — Parses raw output from network tools into structured data.

Supports: nmap (normal + grepable output), arp-a, ip-addr, masscan.
Used by the Orchestrator to extract discovered hosts and feed Phase 2 tasks.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NetworkHost:
    ip: str
    hostname: Optional[str]        = None
    mac: Optional[str]             = None
    vendor: Optional[str]          = None
    os: Optional[str]              = None
    open_ports: List[int]          = field(default_factory=list)
    services: Dict[int, str]       = field(default_factory=dict)   # port → service/version
    status: str                    = "up"
    raw: str                       = ""

    def to_dict(self) -> dict:
        return {
            "ip":         self.ip,
            "hostname":   self.hostname,
            "mac":        self.mac,
            "vendor":     self.vendor,
            "os":         self.os,
            "open_ports": self.open_ports,
            "services":   self.services,
            "status":     self.status,
        }


# ─────────────────────────────────────────────────────────────────────────────
# IP extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

IP_RE = re.compile(
    r"\b((?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d))\b"
)
MAC_RE  = re.compile(r"([0-9A-Fa-f]{2}(?:[:\-][0-9A-Fa-f]{2}){5})")
PORT_RE = re.compile(r"(\d{1,5})/(?:tcp|udp)\s+open\s+([\w/\-\.]+(?:\s+[\w/\-\.]+)*)?", re.IGNORECASE)


def extract_ips(text: str) -> List[str]:
    """
    Extracts all valid non-loopback, non-broadcast IPv4 addresses from text.
    Filters out: 0.x.x.x, 127.x.x.x, 255.x.x.x
    """
    found = IP_RE.findall(text)
    return [
        ip for ip in dict.fromkeys(found)  # deduplicate preserving order
        if not ip.startswith(("0.", "127.", "255."))
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

class NetworkParser:
    """
    Unified parser for output from: nmap, arp-a, ip-addr, arp-scan.
    Auto-detects output format.
    """

    def parse(self, raw_output: str) -> List[NetworkHost]:
        """
        Auto-detect format and parse. Returns list of NetworkHost objects.
        Always returns something even on partial/malformed output.
        """
        if not raw_output or not raw_output.strip():
            return []

        out = raw_output.strip()

        # Choose parser by content signature
        if "Nmap scan report" in out or "Host is up" in out:
            return self._parse_nmap_normal(out)

        if "Status: Up" in out or "# Nmap" in out and "/open/" in out:
            return self._parse_nmap_grepable(out)

        if "Interface:" in out and "MAC" in out:
            return self._parse_arp_scan(out)

        if "[ether]" in out or "at " in out and "on " in out:
            return self._parse_arp_a(out)

        # Fallback: just extract IPs
        return self._fallback_ip_extract(out)

    # ── nmap -sn (normal output) ──────────────────────────────────────────

    def _parse_nmap_normal(self, text: str) -> List[NetworkHost]:
        hosts: List[NetworkHost] = []
        current: Optional[NetworkHost] = None

        for line in text.splitlines():
            # "Nmap scan report for <hostname> (<ip>)" or "Nmap scan report for <ip>"
            report_match = re.match(
                r"Nmap scan report for (?:(.+?) \()?(\d+\.\d+\.\d+\.\d+)\)?", line
            )
            if report_match:
                if current:
                    hosts.append(current)
                hostname = report_match.group(1)
                ip       = report_match.group(2)
                current  = NetworkHost(ip=ip, hostname=hostname)
                continue

            if current is None:
                continue

            # "Host is up"
            if "Host is up" in line:
                current.status = "up"

            # "Host is down"
            if "Host is down" in line:
                current.status = "down"

            # MAC Address line: "MAC Address: AA:BB:CC:DD:EE:FF (Vendor Name)"
            mac_match = re.search(r"MAC Address:\s*([0-9A-Fa-f:]{17})\s*(?:\((.+?)\))?", line)
            if mac_match:
                current.mac    = mac_match.group(1).upper()
                current.vendor = mac_match.group(2)

            # OS detection
            if "OS details:" in line or "Running:" in line:
                current.os = line.split(":", 1)[-1].strip()

            # Open ports: "80/tcp   open  http"
            port_match = PORT_RE.search(line)
            if port_match:
                port    = int(port_match.group(1))
                service = (port_match.group(2) or "").strip()
                current.open_ports.append(port)
                if service:
                    current.services[port] = service

        if current:
            hosts.append(current)

        return [h for h in hosts if h.status == "up"]

    # ── nmap -oG (grepable output) ────────────────────────────────────────

    def _parse_nmap_grepable(self, text: str) -> List[NetworkHost]:
        hosts: List[NetworkHost] = []
        for line in text.splitlines():
            if not line.startswith("Host:"):
                continue
            parts = line.split("\t")
            # "Host: 192.168.1.1 (router.local)"
            host_part = parts[0]
            ip_match  = re.search(r"Host:\s+(\d+\.\d+\.\d+\.\d+)\s+(?:\((.+?)\))?", host_part)
            if not ip_match:
                continue
            ip       = ip_match.group(1)
            hostname = ip_match.group(2) or None
            host     = NetworkHost(ip=ip, hostname=hostname)

            # "Ports: 22/open/tcp//ssh///, 80/open/tcp//http///"
            for part in parts:
                if part.startswith("Ports:"):
                    for port_entry in part[6:].split(","):
                        pm = re.match(r"\s*(\d+)/open/(\w+)//([^/]*)///", port_entry.strip())
                        if pm:
                            port    = int(pm.group(1))
                            service = pm.group(3).strip()
                            host.open_ports.append(port)
                            if service:
                                host.services[port] = service
                if part.startswith("Status:"):
                    host.status = part.split(":")[1].strip().lower()

            if host.status == "up":
                hosts.append(host)
        return hosts

    # ── arp -a ────────────────────────────────────────────────────────────

    def _parse_arp_a(self, text: str) -> List[NetworkHost]:
        hosts: List[NetworkHost] = []
        for line in text.splitlines():
            # Unix/macOS: "? (192.168.1.1) at 2c:96:82:45:81:50 [ether] on enp0s3"
            # Windows:    "192.168.1.1           2c-96-82-45-81-50     dynamic"
            ip_match  = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line) or re.match(
                r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f-]{17}|[0-9A-Fa-f:]{17})\s+",
                line,
            )
            mac_match = MAC_RE.search(line)
            if not ip_match:
                continue
            ip = ip_match.group(1)
            if ip.startswith(("127.", "0.", "255.")):
                continue
            if "incomplete" in line.lower():
                continue
            host = NetworkHost(
                ip=ip,
                mac=mac_match.group(0).upper() if mac_match else None,
                status="up"
            )
            hosts.append(host)
        return hosts

    # ── arp-scan ──────────────────────────────────────────────────────────

    def _parse_arp_scan(self, text: str) -> List[NetworkHost]:
        hosts: List[NetworkHost] = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            ip_match = re.match(r"\d+\.\d+\.\d+\.\d+", parts[0].strip())
            if not ip_match:
                continue
            ip     = parts[0].strip()
            mac    = parts[1].strip().upper() if len(parts) > 1 else None
            vendor = parts[2].strip() if len(parts) > 2 else None
            hosts.append(NetworkHost(ip=ip, mac=mac, vendor=vendor, status="up"))
        return hosts

    # ── Fallback: raw IP extraction ───────────────────────────────────────

    def _fallback_ip_extract(self, text: str) -> List[NetworkHost]:
        return [
            NetworkHost(ip=ip, status="up")
            for ip in extract_ips(text)
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Result aggregator — merges multi-phase results into a unified report
# ─────────────────────────────────────────────────────────────────────────────

class NetworkReport:
    """
    Merges discovery results + per-host scan results into a
    structured, human-readable network map.
    """

    def __init__(self):
        self._hosts: Dict[str, NetworkHost] = {}
        self.parser = NetworkParser()

    def ingest(self, raw_output: str) -> List[NetworkHost]:
        """Parse raw output and merge into the report."""
        found = self.parser.parse(raw_output)
        for host in found:
            if host.ip in self._hosts:
                # Merge: update with richer data
                existing = self._hosts[host.ip]
                if host.mac:     existing.mac     = host.mac
                if host.vendor:  existing.vendor  = host.vendor
                if host.os:      existing.os      = host.os
                if host.hostname:existing.hostname = host.hostname
                existing.open_ports = list(set(existing.open_ports + host.open_ports))
                existing.services.update(host.services)
            else:
                self._hosts[host.ip] = host
        return found

    def hosts(self) -> List[NetworkHost]:
        """Return all discovered hosts, sorted by IP."""
        import ipaddress
        try:
            return sorted(self._hosts.values(), key=lambda h: ipaddress.ip_address(h.ip))
        except Exception:
            return list(self._hosts.values())

    def to_markdown(self) -> str:
        """Render the complete network report as markdown."""
        lines = ["# 🔍 Network Reconnaissance Report\n"]
        hosts = self.hosts()

        if not hosts:
            return "# ⚠️ No hosts discovered.\n"

        lines.append(f"**{len(hosts)} host(s) found**\n")
        lines.append("---")

        for h in hosts:
            lines.append(f"\n## 🖥️ {h.ip}")
            if h.hostname and h.hostname != h.ip:
                lines.append(f"- **Hostname**: `{h.hostname}`")
            if h.mac:
                lines.append(f"- **MAC**: `{h.mac}`")
            if h.vendor:
                lines.append(f"- **Vendor**: {h.vendor}")
            if h.os:
                lines.append(f"- **OS**: {h.os}")

            if h.open_ports:
                lines.append(f"\n### Open Ports ({len(h.open_ports)})")
                lines.append("| Port | Service |")
                lines.append("|------|---------|")
                for port in sorted(h.open_ports):
                    svc = h.services.get(port, "—")
                    lines.append(f"| {port} | {svc} |")
            else:
                lines.append("\n*No open ports detected (or scan not yet run)*")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total_hosts": len(self._hosts),
            "hosts": [h.to_dict() for h in self.hosts()]
        }

    def get_ips(self) -> List[str]:
        """Return list of all discovered IPs."""
        return [h.ip for h in self.hosts()]


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

def parse_discovery_output(raw: str) -> List[str]:
    """
    Quick extraction: given discovery output (nmap/arp-a/arp-scan),
    returns list of live IP strings.
    Used by Orchestrator to inject per-host tasks.
    """
    parser = NetworkParser()
    hosts  = parser.parse(raw)
    return [h.ip for h in hosts]


def build_host_scan_commands(ip: str) -> List[dict]:
    """
    Build the standard per-host enumeration commands for a given IP.
    Returns list of command dicts ready for the task router.
    """
    return [
        {
            "cmd":  f"sudo nmap -sV -sC -O -T4 --open {ip}",
            "risk": "medium",
            "phase": "enumeration",
            "target": ip
        }
    ]
