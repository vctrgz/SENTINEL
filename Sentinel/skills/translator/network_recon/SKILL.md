# Skill: network_recon

## Description
Generate precise, layered shell commands for network reconnaissance.
This skill encodes the full recon workflow: discovery, enumeration, service detection, and OS fingerprinting.

---

## Reconnaissance Phases

### Phase 1 - Host Discovery
Always start with a host sweep to enumerate live systems.
Use in this priority order:
1. `sudo nmap -sn <CIDR>` on Linux, macOS, and FreeBSD, or `nmap -sn <CIDR>` on Windows and Android
2. `sudo arp-scan --localnet` when the runtime supports it
3. `arp -a` as passive fallback only

Never use only `arp -a` for discovery.

### Phase 2 - Port Scanning per host
Run after extracting IPs from Phase 1 output.
Use: `sudo nmap -sV -sC -O -T4 --open <ip>` on Unix-like systems with privileges, or the closest native equivalent on Windows/Android.

### Phase 3 - Targeted Service Enumeration
Based on Phase 2 open ports, run targeted scripts:
- Port 80/443: `nmap -p 80,443 --script http-title,http-methods <ip>`
- Port 22: `nmap -p 22 --script ssh-hostkey,ssh-auth-methods <ip>`
- Port 445: `nmap -p 445 --script smb-os-discovery,smb-security-mode <ip>`
- Port 3306: `nmap -p 3306 --script mysql-info <ip>`

---

## CIDR Detection
When the user does not specify a CIDR, detect it from the active OS:
- Linux/Android: `ip route show`, `ip addr show`
- macOS/FreeBSD: `ifconfig`, routing-table commands
- Windows: `ipconfig` plus subnet mask parsing

---

## Rules
- ALWAYS detect the OS family before generating commands
- Support these families explicitly: Windows, Linux, macOS, FreeBSD, Android
- Use `sudo` only where the runtime supports it and the command requires privileges
- Do not prepend `sudo` on Windows
- ALWAYS run discovery before per-host scans
- DO NOT use only `arp -a` for discovery
- Prefer machine-parseable output when possible

---

## Failure Modes
- nmap not installed: suggest the native package-manager command for the detected OS
- Permission denied for SYN scan: fall back to `-sT` if appropriate
- No CIDR provided: detect it with OS-native networking commands
- All hosts show as down: try a different discovery method compatible with the OS
