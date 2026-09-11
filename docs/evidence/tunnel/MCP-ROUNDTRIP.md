# MCP Roundtrip Verification

## Handshake
* **Protocol**: MCP `2026-07-28`
* **Transport**: Local `stdio`
* **Server**: `tacp`

## Tool Invariants
* Exactly 13 read-only tools exposed in `tools/list`.
* Mutation tools (`workspace.patch`, `patch_batch`) absent.
* Execution tools (`execution.request`) absent.
