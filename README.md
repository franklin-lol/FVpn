<div align="center">

```
  ███████╗██╗   ██╗██████╗ ███╗   ██╗
    ██╔════╝██║   ██║██╔══██╗████╗  ██║
    █████╗  ██║   ██║██████╔╝██╔██╗ ██║
    ██╔══╝  ╚██╗ ██╔╝██╔═══╝ ██║╚██╗██║
    ██║      ╚████╔╝ ██║     ██║ ╚████║
    ╚═╝       ╚═══╝  ╚═╝     ╚═╝  ╚═══╝
```

**Unified Proxy Management Panel**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61dafb?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ed?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Protocols](https://img.shields.io/badge/protocols-8-7c3aed?style=flat-square)](#protocols)

[github.com/franklin-lol/FVpn](https://github.com/franklin-lol/FVpn) &nbsp;·&nbsp; [franklin-sys.vercel.app](https://franklin-sys.vercel.app/)

</div>

---

<div align="center">
  <img src="docs/demo.svg" width="740" alt="FVpn install demo"/>
</div>

---

## Overview

FVpn is a self-hosted proxy management panel. One command deploys a production-grade server supporting 8 protocols. A Python library generates client configs for all major proxy clients from a single unified API.

The panel manages users, nodes, subscriptions and traffic from a single web interface. A Telegram bot provides full remote control. A self-healing daemon monitors and recovers from failures automatically.

---

## Protocols

| Protocol | Transport | Notes |
|----------|-----------|-------|
| Hysteria2 | QUIC | Port-hopping, high-throughput |
| VLESS Reality | TCP | XTLS-Vision, zero TLS fingerprint |
| ShadowTLS v3 | TCP | SNI camouflage via real TLS handshake |
| Shadowsocks 2022 | TCP/UDP | aes-256-gcm, chacha20 |
| Trojan | TCP | HTTPS traffic mimicry |
| TUIC v5 | QUIC | BBR congestion, 0-RTT |
| WireGuard | UDP | ChaCha20-Poly1305, kernel-level |
| SSH | TCP | Legacy tunnel fallback |

---

## Install

```bash
bash <(curl -s https://raw.githubusercontent.com/franklin-lol/FVpn/main/install.sh)
```

Ubuntu 20.04+ or Debian 11+. Root required. Domain optional (self-signed fallback).

Installs Xray-core, Sing-box, obtains TLS certificate, configures firewall, deploys panel via Docker Compose. Panel is available within 5 minutes.

---

## Manual deploy

```bash
git clone https://github.com/franklin-lol/FVpn && cd FVpn
cp .env.example .env        # edit: DOMAIN, MASTER_PASSWORD, JWT_SECRET
docker compose up -d --build
```

---

## Config generation library

```python
from app.lib.config_generator import ConfigGenerator, Balancer

gen = ConfigGenerator(domain="your-domain.com")

gen.add_protocol("hysteria2",   host="1.2.3.4", port=443,  password="xxx")
gen.add_protocol("vless",       host="1.2.3.4", port=443,  uuid="...", public_key="...")
gen.add_protocol("shadowsocks", host="1.2.3.4", port=8443, method="aes-256-gcm", password="yyy")
gen.add_protocol("trojan",      host="1.2.3.4", port=443,  password="zzz", sni="domain.com")

balancer = Balancer(
    strategy="latency",
    url="http://www.gstatic.com/generate_204",
    interval="1m",
    tolerance=50,
)

gen.generate("singbox",      balancer=balancer)   # → JSON
gen.generate("clash",        balancer=balancer)   # → YAML
gen.generate("hiddify",      balancer=balancer)   # → JSON
gen.generate("shadowrocket", balancer=balancer)   # → URI list
gen.generate("v2rayng",      balancer=balancer)   # → base64

gen.validate()                                     # → list of errors
gen.export("singbox", "/etc/fvpn/client.json")    # → write file
gen.to_base64(gen.generate("v2rayng"))             # → base64 string
```

---

## Telegram bot

Set `TELEGRAM_TOKEN` and `TELEGRAM_ADMIN_IDS` in `.env`, then `docker compose restart bot`.

```
/start         Main menu
/status        Dashboard: users, nodes, traffic, CPU/RAM
/nodes         List nodes with latency
/checknodes    Trigger health check on all nodes
/users         List users and traffic usage
/adduser       Create user (guided wizard)
/deluser <id>  Delete user by ID
/sub <uid>     Get subscription links for user
/logs          Last 30 log lines
/restart xray  Restart proxy service
```

---

## Self-healing

Systemd timer runs every 5 minutes:

- Restarts crashed Docker containers
- SSH-restarts proxy services on remote nodes when they go offline
- Renews TLS certificate when expiry is within 30 days
- Cleans disk and prunes Docker when usage exceeds 85%
- Logs all events to `/var/log/fvpn.log`

Auto-backup every 6 hours. Local retention: 7 days. Optional S3 upload via `BACKUP_S3_BUCKET`.

---

## Architecture

```
                    Nginx :2095 (SSL)
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    React Frontend   FastAPI Backend   Telegram Bot
    Vite + Zustand   SQLite + Redis    aiogram 3
          │              │
          └──────────────┤
                         │
              ┌──────────┴──────────┐
          Xray-core           Sing-box
       VLESS · Trojan     Hysteria2 · TUIC
       Shadowsocks            ShadowTLS
                              WireGuard
```

---

## Environment

`.env` is generated by `install.sh`. Fields marked `[auto]` are set automatically — do not edit unless migrating.

| Variable | [auto] | Description |
|----------|--------|-------------|
| `DOMAIN` | | Server domain or IP |
| `MASTER_PASSWORD` | auto | Initial admin password |
| `JWT_SECRET` | auto | 32-byte hex signing secret |
| `REDIS_PASSWORD` | auto | Redis auth password |
| `CORS_ORIGINS` | | `*` or `https://a.com,https://b.com` |
| `TELEGRAM_TOKEN` | | From @BotFather |
| `TELEGRAM_ADMIN_IDS` | | Comma-separated Telegram user IDs |
| `REALITY_PRIVATE_KEY` | auto | VLESS Reality x25519 private key |
| `BACKUP_S3_BUCKET` | | S3 bucket name (optional) |

Full reference: [`.env.example`](.env.example)

---

## License

MIT

---

<div align="center">

Built by [franklin](https://franklin-sys.vercel.app/)

</div>
