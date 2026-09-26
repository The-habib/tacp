# TACP Agent-Native Benchmark & Network Round-Trip Report (Phase 3)

This report quantifies how TACP's aggregate primitives and multi-lane admission architecture accelerate AI agent task completion over remote network environments (Cloudflare edge tunnels).

---

## 1. Remote AI Agent Round-Trip Bottleneck

When a remote AI agent interacts with an Android device over cellular networks or public Internet tunnels, the network transmission time (radio transition, TCP handshake, TLS negotiation, Cloudflare proxying) dominates overall latency:

- **Local TACP Processing Latency:** ~0.60 to 3.80 ms
- **Remote Cloudflare Tunnel Latency:** ~407.5 ms (warm RTT) / ~924.5 ms (cold RTT)

Because remote network transport accounts for **> 98% of total turn wall-clock time**, reducing the number of round trips is the single most impactful optimization for agent responsiveness.

---

## 2. Empirical Agent Workflow Comparison

We benchmarked two approaches for an autonomous agent assessing complete Android device health and telemetry:

### Approach A: Piecemeal Multi-Turn Invocations (Traditional MCP)
The agent executes 5 individual tool calls sequentially:
1. `system.health` (412.3 ms)
2. `device.telemetry.battery` (425.1 ms)
3. `device.network.interfaces` (431.8 ms)
4. `device.storage.overview` (441.2 ms)
5. `device.processes.list` (445.0 ms)
- **Total Invocations:** 5 requests
- **Total Network Payload:** ~18.4 KB across 5 responses
- **Total Agent Wall-Clock Time:** **2,155.4 ms**

### Approach B: TACP Aggregate Primitive (`device.snapshot`)
The agent executes a single unified snapshot invocation:
1. `device.snapshot` (639.2 ms total end-to-end including Cloudflare edge)
- **Total Invocations:** 1 request
- **Total Network Payload:** ~3.2 KB compact JSON
- **Total Agent Wall-Clock Time:** **639.2 ms**

### Performance Verdict
- **Wall-Clock Latency Reduction:** **3.4x faster** (2,155 ms -> 639 ms).
- **Network Round Trips Eliminated:** **4 round trips avoided**.
- **Context Window Token Savings:** ~65% reduction in MCP JSON envelope overhead.

---

## 3. Tool Discovery Optimization (`tools/list` Pagination)

TACP provides 79 registered capabilities. Sending all 79 tool definitions in a single unpaginated prompt consumes substantial context window tokens for LLM agents.

With Phase 3 `tools/list` pagination and category filtering:
- **Category Filter:** Agents querying `tools/list?category=filesystem` receive only the 12 relevant filesystem tools (an **85% reduction** in tool definition payload).
- **Cursor-Based Pagination:** Supported via `cursor` and `limit` query parameters, allowing incremental tool discovery without hitting LLM context limits.
- **Cache Scope & TTL:** Returns `cacheScope: "public"`, `ttlMs: 60000` allowing client-side caching across agent execution turns.
