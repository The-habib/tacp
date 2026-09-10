# TACP System Architecture

**Status**: PROPOSED BASELINE  
**Architecture Lead**: Antigravity Principal Architect  

---

## 1. The Six Architectural Planes

TACP is structured into six strictly separated architectural planes. Dependencies flow strictly downwards.

```
  +-------------------------------------------------------------+
  |                        ACCESS PLANE                         |
  |   (MCP Transport / SSE / Stdio / Auth / External Gateway)  |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |                     INTELLIGENCE PLANE                      |
  |     (Intent Parsing / Context Assembly / Agent Skills)      |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |                       CONTROL PLANE                         |
  |  (Identity / Policy Engine / Capability Lease / Audit Log)  |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |                      EXECUTION PLANE                        |
  | (Workspace Manager / Command Runner / Git / File Sandboxing) |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |                      PROVIDER PLANE                         |
  |     (Termux Provider / Android Provider / Mock Provider)    |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |                         PLATFORM                            |
  |          (Android 16 / Linux 5.15 / Termux Bionic)          |
  +-------------------------------------------------------------+
```

---

## 2. Invariant: Downward Dependency Law

- High-level planes depend upon abstractions of lower planes.
- Lower planes never depend upon or import higher planes.
- **Forbidden Pattern**: An MCP handler directly calling `subprocess.run` or modifying global state without Control Plane mediation.
- All OS interactions MUST be arbitrated by the Control Plane policy engine and recorded in the audit log.

---

## 3. Subsystem Boundaries

1. **Access Plane**: Handles MCP protocol framing, TLS termination, token authentication, and rate limiting.
2. **Intelligence Plane**: Structures agent prompts, validates schemas, interprets instructions, and manages context windows.
3. **Control Plane**: Evaluates whether an action is permitted under the current security policy (`ALLOW`, `ASK`, `DENY`), maintains capability leases, and writes tamper-evident audit trails.
4. **Execution Plane**: Sandboxed execution of file operations, process management, and git operations within project workspaces.
5. **Provider Plane**: Abstracts platform-specific details (Termux-specific paths, environment variables, Bionic libc constraints) behind clean interfaces.
6. **Platform**: The underlying Android/Termux host operating system.

---

## 4. First Vertical Slice: Workspace Inspection

The first implementation slice will be the read-only **Workspace Inspection Service**:
```
AI/MCP Client
     ↓
Access Plane (MCP Tool Call: inspect_workspace)
     ↓
Control Plane (Policy Check: verify path within allowed workspace)
     ↓
Execution Plane (Workspace Service queries path status)
     ↓
Provider Plane (Termux Provider resolves filesystem metadata)
     ↓
Audit Log (Records query and path)
     ↓
Access Plane (Returns structured JSON response)
```
