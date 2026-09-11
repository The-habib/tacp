# Tunnel Health & Readiness Specification

## Endpoints
* **Liveness**: `http://127.0.0.1:8080/healthz` (Verifies daemon process health).
* **Readiness**: `http://127.0.0.1:8080/readyz` (Verifies downstream MCP stdio availability and outbound tunnel connection).
* **Admin UI**: `http://127.0.0.1:8080/ui` (Local operator inspection console).
