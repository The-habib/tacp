# TACP Product Requirements Document (PRD)

**Status**: DRAFT / FOUNDATIONAL SKELETON  
**Phase**: 0 — Bootstrap Foundation  
**Product Owner**: CEO / Project Owner  

---

## 1. Vision & Executive Summary

The **Termux AI Control Plane (TACP)** turns an Android smartphone running Termux into a secure, controlled, and resilient AI-operated execution platform. By bridging modern AI agent capabilities (via the Model Context Protocol, Antigravity CLI, and safe network tunnels) with native Android/Linux system primitives, TACP enables autonomous operations while guaranteeing strict human sovereignty, auditability, and safety.

---

## 2. Problem Statement

Modern AI agents require terminal and system execution to solve complex tasks. Running agents on a mobile device inside Termux provides an incredible portable compute platform, but presents critical risks:
- Uncontrolled LLM shell execution can destroy data, corrupt system state, or leak private tokens.
- Mobile OS environments enforce aggressive process killing, battery saving, and network switching.
- Absence of a full-time human engineering team requires the system itself to enforce boundaries, policy verification, and recovery.

---

## 3. Key Personas & Roles

1. **Non-Technical CEO / Owner**: Retains supreme authority over capabilities, secrets, and high-risk actions.
2. **Autonomous AI Implementer**: Executes scoped coding and operational tasks within hard policy boundaries.
3. **External Client / Developer**: Interacts with TACP via MCP over secure, authenticated tunnels.

---

## 4. Product Goals & Non-Goals

### Goals
- Provide an auditable, fine-grained MCP Gateway for Termux capabilities.
- Enforce strict capability boundaries and zero-trust mediation between AI intents and OS execution.
- Ensure resilience against mobile lifecycle interruptions (battery saving, sleep, network hops).
- Maintain 100% reproducible deployment from clean GitHub checkouts.

### Non-Goals
- TACP is NOT a root exploit framework; it operates strictly unprivileged.
- TACP is NOT dependent on Replit or proprietary platforms.
- TACP does NOT expose unrestricted raw shell access to untrusted networks.

---

## 5. Feature Requirements Roadmap

| Feature ID | Capability | Status | Target Phase |
|---|---|---|---|
| F-001 | Environmental Doctor & Verification | IMPLEMENTED | Phase 0 |
| F-002 | Project Constitution & Agent Rules | IMPLEMENTED | Phase 0 |
| F-003 | Workspace Inspection Service (1st Slice) | PLANNED | Phase 1 |
| F-004 | Policy & Capability Resolution Engine | PLANNED | Phase 2 |
| F-005 | Audited Command Execution Service | PLANNED | Phase 3 |
| F-006 | MCP Server & Gateway | PLANNED | Phase 4 |
| F-007 | Secure Tunnel Brokerage | PLANNED | Phase 5 |
| F-008 | Android Lifecycle & Recovery Daemon | PLANNED | Phase 6 |
