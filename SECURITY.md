# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ Yes     |

---

## Reporting a Vulnerability

FORGE is a pentesting platform — security matters here more than most projects.

**Please do not open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available puts users at risk.

Instead, report vulnerabilities privately:

**Email:** hemparekh1596@gmail.com

Include in your report:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- The component affected (backend API, CLI, frontend, a specific agent, etc.)
- Any suggested mitigations if you have them

---

## What to Expect

- **Acknowledgement** within 48 hours.
- **Assessment and triage** within 7 days — we'll confirm whether it's a valid vulnerability and its severity.
- **Fix and disclosure timeline** agreed with you before anything is published.
- **Credit** — if you'd like to be credited in the release notes, let us know.

---

## Scope

The following are in scope:

- Authentication or authorization bypasses in the FORGE API
- Remote code execution via the API or WebSocket interface
- Path traversal or arbitrary file write via the PoC generation or report export features
- Injection vulnerabilities (SQL, command, prompt) in FORGE's own code
- Secrets or credentials exposed in the codebase or build artifacts

The following are **out of scope**:

- Vulnerabilities in the *target* application being tested by FORGE (that's the point — FORGE is supposed to find those)
- Issues requiring physical access to the server
- Social engineering
- Denial of service via resource exhaustion on a self-hosted instance

---

## Responsible Use

FORGE is built for **authorized security testing only**. Use it only on systems you own or have explicit written permission to test. Unauthorized use may violate computer fraud laws in your jurisdiction.
