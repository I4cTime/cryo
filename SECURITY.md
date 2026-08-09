# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report privately instead:

### 1. GitHub Private Vulnerability Reporting (preferred)

**[Report a vulnerability](https://github.com/I4cTime/cryo/security/advisories/new)**

### 2. Email

Send details to the maintainer directly — contact information is on the
[@I4cTime GitHub profile](https://github.com/I4cTime).

## Scope

Cryo runs a **root daemon** (`cryod`) exposed over a group-owned Unix
socket, so the interesting surface is:

- **Privilege boundary** — anything that lets a user outside the socket
  group drive the daemon, or lets socket clients execute code / write
  files as root beyond the intended sysfs and USB operations.
- **Socket protocol** — malformed JSON-lines requests crashing the
  daemon or corrupting state.
- **Config handling** — `/etc/cryo/config.json` parsing, `set_config`
  patches escalating beyond configuration.
- **Thermal safety** — bypassing or wedging the Thermal Guard failsafe.
- **Installer** (`packaging/install.sh`) — anything it does as root.

## Out of Scope

- Vulnerabilities in upstream dependencies (report to those projects).
- Issues requiring physical access to an already-unlocked machine.
- The alienware-wmi kernel driver itself (report to the kernel).

## Response Timeline

| Stage | Timeframe |
|-------|-----------|
| Acknowledgement | Within 48 hours |
| Initial assessment | Within 7 days |
| Fix or mitigation | Varies by severity |
| Public disclosure | After a fix is released |

Credit in release notes is offered unless you prefer anonymity.
