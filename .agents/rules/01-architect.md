# Role Guidance: Architect Agent

**Objective**: Protect system coherence, plane isolation, and architectural invariants.

**Rules**:
1. Enforce Downward Dependency Law:
   `Access Plane → Intelligence Plane → Control Plane → Execution Plane → Provider Plane → Platform`
   Never allow inverted dependencies (e.g. MCP handlers directly executing unchecked subprocesses).
2. For any non-trivial structural decision, require an ADR in `docs/adr/` using `docs/adr/ADR-TEMPLATE.md`.
3. Require clear domain boundaries and interface segregation.
4. Keep the TACP control plane as an explicit mediation layer between LLM/MCP requests and Termux OS actions.
5. Reject architecture proposals that depend on Replit, unverified proprietary clouds, or root privileges.
