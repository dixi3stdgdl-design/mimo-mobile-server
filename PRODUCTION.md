# MiMo Mobile Server — Production Deployment Guide

## Overview

MiMo Mobile Server is a WebSocket + HTTP server that bridges Android/iOS apps with MiMo Code CLI. This guide covers production deployment, configuration, and monitoring.

## Prerequisites

- Python 3.10+
- Redis (optional, for multi-instance scaling)
- A reverse proxy (nginx recommended) for TLS termination
- Prometheus + Grafana for monitoring (optional)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate JWT secret (REQUIRED)
export MIMO_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')

# 3. Configure environment
cp .env.example .env
# Edit .env with your values

# 4. Start the server
python server.py
```

## Environment Variables Reference

### Required

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_JWT_SECRET` | *(none)* | Secret key for JWT token signing. **Must be set in production.** Generate with: `python -c 'import secrets; print(secrets.token_hex(32))'` |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_WS_PORT` | `8765` | WebSocket server port |
| `MIMO_HTTP_PORT` | `8080` | HTTP API server port |
| `MIMO_WORKSPACE` | `~` | Working directory for file operations |
| `MIMO_WORKERS` | `1` | Number of worker processes |
| `MIMO_SERVER_NAME` | hostname | Server name reported in health checks |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_AUTH_PIN` | `MIMO2026` | Legacy PIN for device authentication |
| `MIMO_JWT_EXPIRY` | `86400` | JWT token expiry in seconds (default: 24h) |
| `MIMO_API_KEYS` | *(empty)* | API keys in format `key1:user1,key2:user2` |

### TLS / HTTPS

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_TLS_ENABLED` | `false` | Enable TLS for WebSocket and HTTP |
| `MIMO_TLS_CERT_DIR` | `./certs` | Directory containing TLS certificates |

### Cloudflare Tunnel

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_CLOUDFLARE_TUNNEL` | `false` | Enable Cloudflare Tunnel |
| `MIMO_EXTERNAL_HOST` | *(empty)* | External hostname for tunnel |
| `CLOUDFLARE_TUNNEL_TOKEN` | *(empty)* | Cloudflare tunnel token |

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_CORS_ORIGINS` | `*` | Comma-separated allowed origins |

### Analytics

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_ANALYTICS_ENABLED` | `true` | Enable persistent analytics (SQLite) |
| `MIMO_ANALYTICS_DB` | `~/.mimo/analytics.db` | Path to analytics database |

### Redis (Scaling)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | *(empty)* | Redis connection URL for session sharing |

## Architecture

```
                    ┌──────────────┐
                    │   nginx /    │
                    │   cloudflared│
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────┴─────┐ ┌───┴───┐ ┌─────┴─────┐
        │ WebSocket │ │ HTTP  │ │ /metrics  │
        │  :8765    │ │ :8080 │ │ (Prom)    │
        └───────────┘ └───────┘ └───────────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────┴───────┐
                    │  Redis (opt) │
                    └──────────────┘
```

## API Endpoints

### HTTP

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (200 = OK) |
| `/metrics` | GET | Prometheus metrics |
| `/api/dashboard` | GET | Server dashboard stats |
| `/api/analytics` | GET | Analytics report |
| `/api/analytics/dau` | GET | Daily active users |
| `/api/analytics/retention` | GET | User retention data |
| `/api/analytics/features` | GET | Feature usage stats |
| `/api/exec` | GET | Execute shell command |
| `/api/adb/devices` | GET | List ADB devices |
| `/api/adb/exec` | GET | Execute ADB command |
| `/api/adb/connect` | GET | Connect to ADB device |

### Rate Limiting

All `/api/*` endpoints are rate-limited to **100 requests per minute per IP**. Exceeding the limit returns:

```json
{
  "error": "Too Many Requests",
  "retry_after_seconds": 60
}
```

Status code: `429 Too Many Requests`

### WebSocket

Connect to `ws://HOST:WS_PORT` (or `wss://` with TLS). Protocol:

1. Connect
2. Send auth message: `{"type": "auth", "pin": "MIMO2026"}`
3. Use handlers: `chat`, `execute`, `read_file`, `write_file`, etc.

## Monitoring

### Prometheus

The server exposes metrics at `/metrics`:

- `mimo_ws_connections_active` — Active WebSocket connections
- `mimo_ws_messages_total` — Total WebSocket messages (by type)
- `mimo_ws_auth_failures_total` — Authentication failures
- `mimo_http_requests_total` — HTTP requests (by path, method, status)
- `mimo_http_request_duration_seconds` — HTTP request duration histogram
- `mimo_uptime_seconds` — Server uptime

### Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'mimo-server'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Dashboard

Import the MiMo Server dashboard or create panels for:
- Active connections (gauge)
- Request rate (rate of `mimo_http_requests_total`)
- Error rate (requests with status >= 400)
- Request latency (histogram quantiles)
- Auth failures (counter)

### Structured Logging

All HTTP requests are logged as structured JSON:

```json
{
  "timestamp": "2026-07-09T12:00:00+00:00",
  "level": "INFO",
  "message": "GET /api/dashboard 200 12.3ms",
  "method": "GET",
  "path": "/api/dashboard",
  "status": 200,
  "duration_ms": 12.3,
  "ip": "192.168.1.100"
}
```

## Security

### Production Checklist

- [ ] Set a strong `MIMO_JWT_SECRET` (64+ hex chars)
- [ ] Change default `MIMO_AUTH_PIN`
- [ ] Enable TLS (`MIMO_TLS_ENABLED=true`)
- [ ] Set `MIMO_CORS_ORIGINS` to your domain(s)
- [ ] Deploy behind a reverse proxy (nginx)
- [ ] Restrict ADB endpoints if not needed
- [ ] Monitor auth failure rate

### Reverse Proxy (nginx)

```nginx
upstream mimo_server {
    server 127.0.0.1:8080;
}

server {
    listen 443 ssl;
    server_name mimo.yourdomain.com;

    ssl_certificate /etc/ssl/certs/mimo.pem;
    ssl_certificate_key /etc/ssl/private/mimo.key;

    # WebSocket upgrade
    location /ws {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # HTTP API
    location / {
        proxy_pass http://mimo_server;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Troubleshooting

### Port already in use

```
[FATAL] Port 8765 is already in use by another process.
[FATAL] Kill the other process or change MIMO_WS_PORT in .env
[FATAL] Example: kill -9 $(lsof -t -i:8765)
```

### JWT_SECRET missing

```
FATAL: Environment validation failed
  - MIMO_JWT_SECRET is required but not set.
```

Fix: `export MIMO_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')`

### Redis unavailable

```
[STATE] Redis unavailable (connection refused), falling back to memory
```

The server falls back to in-memory sessions. Works for single-instance deployments.

### High latency

- Check Prometheus metrics for `mimo_http_request_duration_seconds`
- Verify no resource contention (CPU, memory)
- Check Redis latency if using session sharing
- Review rate limiting (429 responses)

### WebSocket disconnections

- Default heartbeat interval: 30s
- Default timeout: 120s of inactivity
- Check `mimo_ws_connections_active` for connection churn
- Verify reverse proxy `proxy_read_timeout` is足够高

## Performance Tuning

### Environment Variables

```bash
# Increase workers for multi-core machines
MIMO_WORKERS=4

# Use Redis for multi-instance session sharing
REDIS_URL=redis://localhost:6379/0

# Adjust rate limiting (edit rate_limiter.py)
# Default: 100 req/min per IP
```

### System Tuning

```bash
# Increase file descriptor limits
ulimit -n 65536

# Tune kernel TCP settings
sysctl -w net.core.somaxconn=65535
sysctl -w net.ipv4.tcp_max_syn_backlog=65535
```
