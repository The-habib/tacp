# TACP — Termux AI Control Plane

> **A secure, auditable, and resilient AI-operated control plane running natively inside Termux on Android.**

---

## Current Status: Phase 0 (Bootstrap / Engineering Foundation)

TACP is currently in its bootstrap foundation phase. The engineering factory, constitution, agent governance rules, and canonical verification harness are established.

- **Constitution**: [docs/00-PROJECT-CONSTITUTION.md](docs/00-PROJECT-CONSTITUTION.md)
- **Architecture**: [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md)
- **Environment Discovery**: [docs/bootstrap/ENVIRONMENT_DISCOVERY.md](docs/bootstrap/ENVIRONMENT_DISCOVERY.md)
- **Project Status**: [docs/PROJECT-STATUS.md](docs/PROJECT-STATUS.md)

---

## Quick Start for Developers

### Prerequisites
- Termux on Android (`aarch64`)
- Python 3.11+
- `uv`, `jq`, `ripgrep`, `shellcheck` (available via Termux `pkg install uv jq ripgrep shellcheck`)

### Setup Development Environment
```bash
# 1. Run doctor to verify system prerequisites
./doctor

# 2. Run local canonical verification
./verify
```

---

## Constitutional Law
> *"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."*
