# Phase 4 Evidence — Identity & Principal Model

**Document ID**: TACP-EV-P4-04  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Principal Context
Every execution request is tied to an explicit, authenticated `Principal` model:
- `PrincipalType.LOCAL_AGENT`: Standard AI agent communicating via MCP or API.
- `PrincipalType.OPERATOR`: Human administrative user via TACP CLI.
- `PrincipalType.SYSTEM`: Internal background jobs (e.g., orphan reconciler).

## 2. Capability Scoping
Execution permissions are governed per principal:
- Local agents are strictly limited to `execution.request` under vertical slice binary whitelisting.
- Approval tickets require human operator approval (`PrincipalType.OPERATOR`).
- Agents cannot approve their own requests or escalate their privilege class.
- Identity is preserved across the entire 16-stage pipeline and stamped onto every audit record.
