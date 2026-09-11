# TACP 0.1 Quickstart Guide

The **Termux AI Control Plane (TACP)** provides a secure, auditable, high-performance execution bridge between AI agents and local Termux environments on Android.

TACP 0.1 establishes a **strictly read-only baseline**, guaranteeing zero unintended modifications while granting AI assistants full situational awareness.

---

## 1. Installation

### Quick Automated Install

Run the self-contained installer directly inside your cloned repository:

```bash
git clone https://github.com/The-habib/tacp.git ~/projects/tacp
cd ~/projects/tacp
./install.sh
```

The installer will:
1. Validate Python $\ge$ 3.11.
2. Initialize an isolated virtual environment (`.venv`).
3. Install TACP in editable mode.
4. Run diagnostics (`tacp doctor`).
5. Register your project directory as the default workspace.
6. Create a global symlink at `$PREFIX/bin/tacp`.

---

## 2. Verification & Diagnostics

Verify your local installation:

```bash
# Check runtime health and dependencies
tacp doctor

# Check system resources, uptime, and database status
tacp status

# View registered read-only capabilities
tacp capabilities
```

Output of `tacp capabilities`:
```
NAME                 DOMAIN          DESCRIPTION
--------------------------------------------------------------------------------
system.inspect       system          Inspect host system, kernel, CPU architecture, memory, and Termux details
system.health        system          Check TACP subsystem health, storage margins, and database connectivity
system.version       system          Return TACP version and supported MCP protocol specification
capabilities.list    capabilities    List all available TACP capabilities and their parameter schemas
workspace.list       workspace       List all registered workspace roots and their status
workspace.inspect    workspace       Inspect statistics, file counts, and git repository status of a workspace
fs.list              filesystem      List directory entries inside an authorized workspace root with metadata
fs.stat              filesystem      Get detailed metadata, permissions, and classification for a file or directory
fs.read              filesystem      Safely read file content with output size truncation and secret protection
fs.search            filesystem      Search file content within a workspace using substring or regex pattern
process.list         process         List running processes owned by the current Termux user
process.inspect      process         Inspect command line, memory, and status of a specific user process PID
audit.recent         audit           Retrieve recent tamper-evident audit events and authorization decisions
```

---

## 3. Workspace Management

TACP enforces a **canonical path jail**. AI agents can only read files inside authorized workspace directories.

```bash
# List active workspaces
tacp workspace list

# Register a new project directory
tacp workspace add ~/projects/my-web-app --name web-app
```

---

## 4. Connecting AI Clients (MCP Server)

TACP includes a pure-Python, zero-dependency **Model Context Protocol (MCP)** server communicating over standard I/O (`stdio`).

### Claude Desktop / Cursor / Antigravity MCP Config

Add the following entry to your `mcpServers` configuration:

```json
{
  "mcpServers": {
    "tacp": {
      "command": "/data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp",
      "args": ["serve"]
    }
  }
}
```

Or when running directly inside Termux:

```json
{
  "mcpServers": {
    "tacp": {
      "command": "tacp",
      "args": ["serve"]
    }
  }
}
```

---

## 5. Security Invariants in TACP 0.1

1. **Strictly Read-Only**: No shell execution (`shell.exec`), no file mutation (`fs.write`, `fs.delete`), no Android device manipulation, no root escalation.
2. **Canonical Path Jail**: All filesystem paths are resolved to their canonical paths. Symlinks pointing outside the workspace and path traversal attempts (`../`) are blocked with `OUTSIDE_WORKSPACE`.
3. **Secret Redaction**: Environment files (`.env`), private keys (`id_rsa`, `*.pem`), and credentials are automatically classified as `SECRET` and blocked from reading.
4. **Tamper-Evident Audit Logging**: Every tool invocation and authorization decision is recorded in SQLite with microsecond timestamps and parameter redaction:

```bash
# View recent audit events
tacp audit --limit 20
```

---

## 6. Running Project Tests

```bash
# Run the complete test suite (173 tests)
./verify
```
