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

[![Python](https://img.shields.io/badge/python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61dafb?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ed?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Protocols](https://img.shields.io/badge/protocols-7-7c3aed?style=flat-square)](#protocol-support)

[github.com/franklin-lol/FVpn](https://github.com/franklin-lol/FVpn) &nbsp;·&nbsp; [franklin-sys.vercel.app](https://franklin-sys.vercel.app/)

</div>

# FVpn

Self-hosted management panel for Xray and sing-box. FastAPI, React and Docker Compose; one backend worker and a persistent SQLite database. Designed for a small personal deployment.

Current version: **1.0.2**. See [CHANGELOG.md](CHANGELOG.md) for release notes covering installation and backup fixes, security defaults, and the refreshed setup and connection interface.

## Installation

Ubuntu 20.04+ or Debian 11+, root access, and a public hostname or IP address are required. Review the installer before running it on your server:

```bash
git clone https://github.com/franklin-lol/FVpn
cd FVpn
sudo bash install.sh
```

The installer prepares the checkout, fills missing or empty required environment values, publishes TLS files, adds firewall rules without resetting existing rules, and starts Compose. It preserves nonempty existing configuration. It never stops an unrelated web server to obtain a certificate.

The panel uses **HTTPS on port 2095**. A public IP uses a self-signed certificate, which requires a browser exception. A domain can use Let's Encrypt when DNS and inbound port 80 are available. TCP port 443 belongs to the proxy core, not the panel.

On a new database, sign in as `admin` with the installer password. The first-run guide changes that password, reuses the local server and applies the recommended VLESS Reality preset. Existing installations open the dashboard directly. Advanced protocol options remain available under Connections; saving parameters and applying them are separate operations with an explicit result.

Fresh installations create two active connections: VLESS Reality on TCP 443 and Shadowsocks on TCP 8443. The guide selects VLESS as the recommended option and preserves Shadowsocks. Add other protocols deliberately under Connections.

Open Users, choose a person and create a connection link. Share its `/s/…` guide page: it offers a QR, device/app selection, an import button and three setup steps. The interface supports Russian/English, light/dark/system themes and phone layouts. Subscription links are bearer secrets; anyone with one can download its configuration.

Keep `.env`, `/etc/fvpn/env`, private keys and backups private. Environment files use mode 600. Do not commit them. Changing `MASTER_PASSWORD` does not reset an existing database user's password. Changing `JWT_SECRET` signs out existing sessions. Empty, short (under 32 bytes) and known example JWT secrets are rejected at startup; generate your own value.

## Manual configuration

The example is named [`env.example`](env.example), without a leading dot. Copy it to `.env`, fill `DOMAIN`, `MASTER_PASSWORD` and a cryptographically random `JWT_SECRET`, and prepare ordinary PEM files at `/etc/fvpn/ssl/cert.pem` and `/etc/fvpn/ssl/key.pem` before starting:

```bash
cp env.example .env
chmod 600 .env
openssl rand -hex 32
# Edit .env with your own values; never paste secrets into an issue.
docker compose up -d --build
```

Existing installations retain their SQLite data in the `backend-data` volume. Never use `docker compose down -v` when updating. Redis is not used; new deployments do not start it. Existing `REDIS_*` environment entries can remain and existing Redis volumes are not automatically removed.

## Protocol support

| Protocol | Local server configuration | Notes |
| --- | --- | --- |
| VLESS Reality | Xray | Recommended TCP preset; does not require a publicly trusted server certificate. |
| Shadowsocks | sing-box | Authenticated encryption; default `aes-256-gcm` is classic Shadowsocks, not Shadowsocks 2022. |
| Trojan / VMess | Xray | Require a certificate trusted by the selected client. |
| Hysteria2 / TUIC | sing-box | Require UDP access and suitable client certificate trust. |
| ShadowTLS | sing-box | Advanced configuration; client format support must be checked. |
| WireGuard / SSH | Not supported as managed local presets | Existing records are retained; incomplete operations are not reported as successful. |

The server builders cover seven protocol families; client formats support different subsets. Do not infer device compatibility from the number of names in the interface. Core configuration is checked against the installed image before replacement. Failed application restores the previous files and attempts to recover the affected cores.

Generated sing-box/Hiddify client JSON uses the sing-box **1.12+** DNS, routing and TUN schema; use a client bundling that core or newer. Validation uses the pinned sing-box 1.13.13 image. Other clients can use URI/base64 or Clash-compatible formats when supported by their protocols. Import buttons depend on an installed application; copying the URL remains available.

WireGuard is excluded from all client exports until separate client keys are implemented. Existing database records are preserved. A subscription with no supported active configuration returns an explicit error.

## Nodes and subscriptions

Local configuration is applied only to a node explicitly marked local. Editing a remote node never restarts the local proxy containers. Remote configuration delivery is manual; SSH auto-setup is limited to the implemented Shadowsocks flow. Other setup requests return an actionable unsupported/manual result.

SSH uses trust on first use: the first successful connection stores the server public key in `/data/ssh_known_hosts`; subsequent connections reject changed keys before authentication. Verify a new server's SHA256 host fingerprint through a trusted channel before connecting. After a legitimate key rotation, back up and remove only that host's entry from this file, then reconnect. Never clear the entire file to bypass a mismatch.

Subscriptions export client configuration in sing-box, Clash, Hiddify, Shadowrocket, v2rayNG and base64 formats, subject to each format's protocol support. Credentials are shared per protocol. Disabling a user or subscription prevents future downloads but does **not** revoke credentials already imported into a client. Rotate the affected protocol credentials to revoke them; that affects everyone sharing that protocol.

Traffic limits are stored metadata. Quotas, per-user traffic accounting and connection limits are **not enforced**. The dashboard does not display simulated traffic; the history API reports that measurements are unavailable. Node health checks are reachability indicators, not end-to-end VPN verification.

## Security defaults

Ports 8000 and 2096 bind only to server loopback; use the HTTPS panel port for remote administration and subscriptions. Nginx overwrites client IP headers, and the single backend worker trusts only `TRUSTED_PROXY_IPS` (the fixed Compose Nginx address by default). Preserve that pairing if changing the Docker network. Login attempts are bounded independently by account and real client IP; limits reset on backend restart.

Empty or legacy `CORS_ORIGINS=*` derives the panel HTTPS origin from `DOMAIN` and `PANEL_PORT`. Set explicit comma-separated or JSON origins only when hosting the frontend separately. A configured Telegram bot requires `TELEGRAM_ADMIN_IDS`; an empty list fails startup and never grants access. In Compose the bot uses short-lived bearer tokens signed with the already-shared JWT secret, so changing the admin password does not disable it. A separately deployed bot without that secret uses `BOT_API_USER`/`BOT_API_PASS` (legacy fallback: `MASTER_PASSWORD`); keep that password synchronized.

After changing `TELEGRAM_TOKEN` or `TELEGRAM_ADMIN_IDS` in the checkout's `.env`, recreate the bot container; `restart` keeps its old environment:

```bash
docker compose up -d --no-deps --force-recreate bot
docker compose logs --since=1m bot
```

Runtime images are pinned by digest and frontend dependencies by `package-lock.json`. Update them deliberately with the checks below; core images are excluded from unattended Watchtower updates. The backend still has Docker socket access for local core control; deploy the panel only on a trusted personal server and restrict administrator access.

Watchtower is optional and excluded from the default Compose startup because it cannot update pinned image digests. To stop an updater from an earlier installation, run `docker compose stop watchtower`. Explicit opt-in is `docker compose --profile updates up -d watchtower`; its Docker API defaults to 1.44, the minimum accepted by Docker 29. On an older daemon, set `WATCHTOWER_DOCKER_API_VERSION` to a version that daemon supports before opting in. Keep it disabled when using only the supplied pinned images and local builds.

## Backups

The panel's Backup action and scheduled wrapper use the same Python helper inside the backend. It takes a consistent SQLite snapshot through the SQLite backup API, includes configured proxy/TLS directories, then verifies restoration into a temporary database before publishing a private archive. Default retention is seven days under `/data/backups` in the persistent backend volume.

```bash
docker compose exec -T backend python -m app.core.backup
docker compose exec -T backend python -m app.core.backup --verify /data/backups/ARCHIVE.tar.gz
docker compose cp backend:/data/backups/ARCHIVE.tar.gz ./ARCHIVE.tar.gz
```

Backups contain unencrypted credentials. Keep `.env`, `/data/ssh_known_hosts` and ACME account/renewal state separately in trusted storage: they are not included. Preserve the SSH pins when restoring a server. Configuration symlinks are rejected; the installer publishes ordinary TLS files. Optional S3 upload is performed by the host wrapper and requires the host AWS CLI and its separately configured credentials. The API creates a local archive only.

For recovery, stop application writers, verify the archive, restore its `database/fvpn.db` and required configuration into a separate location first, and keep the old volume intact until recovery has been tested. Never overwrite a running SQLite file or leave unrelated old WAL/SHM files beside a restored database.

## Monitoring and renewal

The host systemd timer checks this checkout's containers and reports disk/certificate warnings. It does not prune unrelated Docker resources or truncate host logs. Certificate renewal runs on the host and temporarily stops only this project's Nginx when standalone validation requires port 80. Existing settings with custom certificate paths outside the shared TLS mount require explicit operator adjustment.

## Development checks

Target Python 3.12 and Node 20. Development-only tools are pinned in `requirements-dev.txt`.

```bash
pip install -r backend/requirements.txt -r bot/requirements.txt -r requirements-dev.txt
pytest -q tests
ruff check backend bot tests
cd frontend
npm ci
npm run build
```

Validate shell files with `bash -n` and ShellCheck. Do not run the installer or host-management scripts as tests. Core checks must use disposable configuration and test certificates, without host networking or real installation data.

After deployment, check the subscription collection through the HTTPS panel: unauthenticated requests to both `/api/subscriptions` and `/api/subscriptions/` must return 401 directly, without a redirect. Creating a link from Users must return 201 for the selected owner. Exercise this through Nginx: direct backend tests cannot detect proxy redirects that turn POST into GET.

---

<div align="center">

Built by [franklin](https://franklin-sys.vercel.app/)

</div>
