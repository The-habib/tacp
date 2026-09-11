# Automated OpenAI Secure MCP Tunnel Provisioning

## Status
Awaiting Operator Credential Placement (`CONTROL_PLANE_API_KEY`) and Tunnel Creation (`CONTROL_PLANE_TUNNEL_ID`).

## Automated Workflow Pipeline
1. **Discovery**: Verified `tunnel-client` binary (`v0.0.14`), `tacp` stdio server, and local Termux environment.
2. **Profile Generation**: Automated native YAML profile at `~/.config/tunnel-client/tacp-stdio.yaml`.
3. **Transport Wire**: Channel `main` directly bound to `/data/data/com.termux/files/usr/bin/tacp serve`.
4. **Health Gate**: Pre-configured HTTP health listener at `127.0.0.1:8080` (`/healthz`, `/readyz`, `/ui`).
5. **Security Policy**: Zero credential storage; references `env:CONTROL_PLANE_API_KEY`.
