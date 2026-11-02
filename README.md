# FVpn

Self-hosted management panel for Xray and sing-box. FastAPI, React and Docker Compose; one backend worker and a persistent SQLite database. Designed for a small personal deployment.

## Installation

Ubuntu 20.04+ or Debian 11+, root access, and a public hostname or IP address are required. Review the installer before running it on your server:

```bash
git clone https://github.com/franklin-lol/FVpn
cd FVpn
sudo bash install.sh
```

The installer prepares the checkout, fills missing or empty required environment values, publishes TLS files, adds firewall rules without resetting existing rules, and starts Compose. It preserves nonempty existing configuration. It never stops an unrelated web server to obtain a certificate.

The panel uses **HTTPS on port 2095**. A public IP uses a self-signed certificate, which requires a browser exception. A domain can use Let's Encrypt when DNS and inbound port 80 are available. TCP port 443 belongs to the proxy core, not the panel.

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

WireGuard is excluded from all client exports until separate client keys are implemented. Existing database records are preserved. A subscription with no supported active configuration returns an explicit error.

## Nodes and subscriptions

Local configuration is applied only to a node explicitly marked local. Editing a remote node never restarts the local proxy containers. Remote configuration delivery is manual; SSH auto-setup is limited to the implemented Shadowsocks flow. Other setup requests return an actionable unsupported/manual result.

SSH uses trust on first use: the first successful connection stores the server public key in `/data/ssh_known_hosts`; subsequent connections reject changed keys before authentication. Verify a new server's SHA256 host fingerprint through a trusted channel before connecting. After a legitimate key rotation, back up and remove only that host's entry from this file, then reconnect. Never clear the entire file to bypass a mismatch.

Subscriptions export client configuration in sing-box, Clash, Hiddify, Shadowrocket, v2rayNG and base64 formats, subject to each format's protocol support. Credentials are shared per protocol. Disabling a user or subscription prevents future downloads but does **not** revoke credentials already imported into a client. Rotate the affected protocol credentials to revoke them; that affects everyone sharing that protocol.

Traffic limits are stored metadata. Quotas, per-user traffic accounting and connection limits are **not enforced**. Dashboard traffic history is not real telemetry. Node health checks are reachability indicators, not end-to-end VPN verification.

## Security defaults

Ports 8000 and 2096 bind only to server loopback; use the HTTPS panel port for remote administration and subscriptions. Nginx overwrites client IP headers, and the single backend worker trusts only `TRUSTED_PROXY_IPS` (the fixed Compose Nginx address by default). Preserve that pairing if changing the Docker network. Login attempts are bounded independently by account and real client IP; limits reset on backend restart.

Empty or legacy `CORS_ORIGINS=*` derives the panel HTTPS origin from `DOMAIN` and `PANEL_PORT`. Set explicit comma-separated or JSON origins only when hosting the frontend separately. A configured Telegram bot requires `TELEGRAM_ADMIN_IDS`; an empty list fails startup and never grants access. Keep bot API credentials synchronized if changing its account password.

Runtime images are pinned by digest and frontend dependencies by `package-lock.json`. Update them deliberately with the checks below; core images are excluded from unattended Watchtower updates. The backend still has Docker socket access for local core control; deploy the panel only on a trusted personal server and restrict administrator access.

## Backups

The panel's Backup action and scheduled wrapper use the same Python helper inside the backend. It takes a consistent SQLite snapshot through the SQLite backup API, includes configured proxy/TLS directories, then verifies restoration into a temporary database before publishing a private archive. Default retention is seven days under `/data/backups` in the persistent backend volume.

```bash
docker compose exec -T backend python -m app.core.backup
docker compose exec -T backend python -m app.core.backup --verify /data/backups/ARCHIVE.tar.gz
docker compose cp backend:/data/backups/ARCHIVE.tar.gz ./ARCHIVE.tar.gz
```

Backups contain unencrypted credentials. Keep `.env` and ACME account/renewal state separately in trusted storage: they are not included. Configuration symlinks are rejected; the installer publishes ordinary TLS files. Optional S3 upload is performed by the host wrapper and requires the host AWS CLI and its separately configured credentials. The API creates a local archive only.

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
