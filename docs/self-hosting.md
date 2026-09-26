# Self-Hosting the TACP Remote MCP Gateway

For users who prefer complete sovereignty over their infrastructure without third-party tunnel services (such as Cloudflare), TACP includes a lightweight, standalone, self-hostable **Remote MCP Gateway** (`tacp gateway`).

---

## 1. Overview & Relay Architecture

Mobile devices operate behind Carrier-Grade NAT (CGNAT) and dynamic cellular IPs, making incoming TCP connections impossible without port forwarding or public IPs.

The **TACP Remote Gateway** solves this via an **outbound reverse relay**:
1. The **TACP Gateway** runs on any server with a public IP or DNS domain (e.g. AWS, Hetzner, DigitalOcean, or home server with port forwarding).
2. The **Android device** initiates an outbound persistent connection to the Gateway (`POST /relay/connect`).
3. External AI clients (Claude, Cursor, VS Code, ChatGPT) send standard MCP requests to the Gateway (`POST /mcp`).
4. The Gateway routes requests through the established outbound connection to the phone, and relays responses back to the client.

```
+----------------+              +---------------------+              +------------------+
| Remote Client  |              | TACP Remote Gateway |              |  Android Device  |
| (Claude/Cursor)|              | (VPS / Public Host) |              |  (Termux Engine) |
+----------------+              +---------------------+              +------------------+
        |                                  |                                   |
        |                                  |<======= Outbound Relay Stream ====|
        |                                  |   (POST /relay/connect)           |
        |                                  |                                   |
        |--- POST /mcp (JSON-RPC) -------->|                                   |
        |    [Authorization: Bearer tok]   |--- Relayed Request -------------->|
        |                                  |                                   |
        |                                  |<-- Encrypted Tool Result ---------|
        |<-- 200 OK (JSON-RPC Response) ---|                                   |
```

---

## 2. Deploying the Gateway

### 2.1 Direct CLI Execution
On your Linux server:
```bash
git clone https://github.com/The-habib/tacp.git
cd tacp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Start Gateway on port 9090
tacp gateway --host 0.0.0.0 --port 9090
```

### 2.2 Systemd Service Unit
Create `/etc/systemd/system/tacp-gateway.service`:
```ini
[Unit]
Description=TACP Remote MCP Gateway
After=network.target

[Service]
Type=simple
User=tacp
WorkingDirectory=/opt/tacp
ExecStart=/opt/tacp/.venv/bin/tacp gateway --host 127.0.0.1 --port 9090
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tacp-gateway
```

### 2.3 Docker Deployment
Create a `Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .

EXPOSE 9090
ENTRYPOINT ["tacp", "gateway", "--host", "0.0.0.0", "--port", "9090"]
```

And `docker-compose.yml`:
```yaml
version: "3.8"
services:
  tacp-gateway:
    build: .
    restart: always
    ports:
      - "127.0.0.1:9090:9090"
    environment:
      - PYTHONUNBUFFERED=1
```

---

## 3. Reverse Proxy & TLS Configuration

Expose the Gateway through Nginx or Caddy with automated HTTPS certificates.

### Caddyfile (Recommended - Automatic TLS)
```caddy
gateway.yourdomain.com {
    reverse_proxy 127.0.0.1:9090 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
    }
}
```

### Nginx Configuration
```nginx
server {
    server_name gateway.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:9090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/gateway.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gateway.yourdomain.com/privkey.pem;
}
```

---

## 4. Connecting Your Phone to Your Gateway

On your Android phone in Termux:

```bash
tacp remote enable --provider relay --gateway-url https://gateway.yourdomain.com
```

Now, point your AI clients (Claude, Cursor, etc.) directly to:
```
https://gateway.yourdomain.com/mcp
```
with your device's Bearer token in the `Authorization` header.
