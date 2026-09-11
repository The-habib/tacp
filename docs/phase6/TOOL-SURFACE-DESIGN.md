# TACP Phase 6: Semantic Tool Surface & Dynamic Capability Exposure
**Document ID:** `TACP-TOOL-SURF-001`  
**Classification:** MCP Protocol & Tool Surface Architecture  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. The Threat of Tool Overload & Context Bloat

Exposing dozens of Unix command wrappers to an LLM creates severe systemic problems:
1. **Context Window Exhaustion:** Tool definitions consume prompt tokens on every turn.
2. **Hallucination & Misrouting:** LLMs become confused when presented with overlapping tools (e.g. `cat` vs `fs.read`, `ls` vs `fs.list`, `grep` vs `fs.search`).
3. **Privilege Creep:** Exposing mutating or executing tools to a purely conversational agent increases the attack surface.

Phase 6 audits the tool surface, establishes semantic grouping, and introduces **Dynamic Capability Exposure**.

---

## 2. Semantic Tools vs. Raw Unix Command Wrappers

TACP explicitly rejects wrapping raw shell utilities when native semantic capabilities provide superior governance:

| Raw Unix Utility | TACP Semantic Capability | Superiority Justification |
|---|---|---|
| `ls -la` | `fs.list` | Returns structured JSON; enforces pagination; classifies files; zero shell quoting issues. |
| `cat file` | `fs.read` | Enforces 1MB size limit; automatically redacts secrets; classifies binary files; prevents terminal freezing. |
| `stat file` | `fs.stat` | Returns structured JSON timestamps, permissions, and file classifications. |
| `grep -r` | `fs.search` | Bounded line count; path jailing; structured match offsets; zero regex DoS on host. |
| `sed -i` / `patch` | `workspace.patch` | Atomic replace; pre-image checksum verification; rollback snapshot creation; unified diff parsing. |

**Policy Mandate:** No Unix utility is added to the execution allowlist if an equivalent or superior semantic capability exists.

---

## 3. Capability Groups

TACP capabilities are partitioned into four semantic groups:

1. **`OBSERVE` ($R_0$):**
   - `system.inspect`, `system.health`, `system.version`
   - `capabilities.list`, `workspace.list`, `workspace.inspect`
   - `fs.list`, `fs.stat`, `fs.read`, `fs.search`
   - `process.list`, `process.inspect`
   - `audit.recent`
2. **`MUTATE` ($R_1, R_2$):**
   - `workspace.patch`
   - `workspace.patch_batch`
3. **`EXECUTE` ($R_1, R_3$):**
   - `execution.request`
4. **`ADMIN` ($R_5$):**
   - `audit.verify_integrity`
   - `emergency_stop`

---

## 4. Dynamic Capability Exposure Architecture

The MCP `tools/list` RPC endpoint dynamically filters tool definitions according to the active context:

```
                  ┌──────────────────────┐
                  │    Incoming MCP      │
                  │     tools/list       │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [ Trust Profile Check ]         [ Configuration & Flags ]
    - LOCKDOWN: Hide MUTATE/EXEC    - mutation_enabled == false: Hide MUTATE
    - STRICT: Expose all with       - execution_enabled == false: Hide EXEC
      approval notices
            │                                 │
            └────────────────┬────────────────┘
                             │
                             ▼
                  [ Principal Authority ]
                   - Hide ADMIN tools if principal
                     lacks Authority.ADMIN_INTEGRITY
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Clean, Non-redundant │
                  │     Tool Catalog     │
                  └──────────────────────┘
```

### Profile Exposure Rules:
- **`LOCKDOWN` Profile:** Returns **ONLY** `OBSERVE` tools. The model cannot see `workspace.patch` or `execution.request`, eliminating accidental tool selection.
- **`BALANCED` / `DEVELOPER` Profile:** Exposes `OBSERVE`, `MUTATE`, and `EXECUTE` tools, with clear descriptions of when leases or approvals apply.
- **Disabled Flags:** If `config.execution_enabled = false`, `execution.request` is excluded from the catalog.

---

## 5. Rich Semantic Tool Description Standard

Tool descriptions are engineered to provide maximum clarity to the model without ambiguity:

```json
{
  "name": "fs.read",
  "description": "Reads file contents as text from an active workspace. [WHAT IT DOES]: Reads UTF-8 text files up to 1MB within the workspace jail. [WHAT IT DOES NOT DO]: Does not write, modify, or execute files. Does not read files outside the workspace. [SIDE EFFECTS]: None. [RISK]: R0 (Safe). [APPROVAL]: None required.",
  "inputSchema": {
    "type": "object",
    "required": ["workspace_id", "subpath"],
    "properties": {
      "workspace_id": {"type": "string", "description": "Target workspace identifier."},
      "subpath": {"type": "string", "description": "Relative file path within the workspace."}
    }
  }
}
```

This structure prevents LLMs from guessing behavior and sets explicit, unambiguous operational boundaries.
