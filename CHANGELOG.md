# Changelog

## [1.0.2] — 2026-11-02

### Fixed
- Installation preserves nonempty environment values, protects environment files, avoids unrelated port-80 processes and publishes usable TLS files for containers.
- Backups use consistent SQLite snapshots and verify restoration before publication. Core configuration is validated before application, rolls back on failure and supports an empty protocol set.
- Remote-node synchronization no longer changes local containers. Subscription creation uses the selected user; parent deletion preserves database integrity.
- Generated sing-box clients use the current DNS, routing and TUN schema. New VMess configurations persist one UUID shared by the server and clients.

### Security
- Bot access fails closed, weak JWT secrets are rejected, and login limits apply independently to accounts and trusted client IPs.
- SSH uses persistent TOFU host-key verification. WireGuard credentials are excluded from client exports; WebSocket access requires an active administrator.
- Auxiliary ports bind loopback, CORS defaults to the panel origin, bearer URLs are redacted from logs, and images and frontend dependencies are pinned.
- Password hashing and blocking CPU sampling run outside the event loop.

### Added
- First-run guide, password changes, and a public connection page with QR, application import links and three setup steps.
- Responsive Tailwind interface with Russian/English, light/dark/system themes, actionable states and advanced protocol editing.

### Changed
- Removed unused Redis and simulated traffic displays. Application version metadata now agrees with the changelog.
- Client JSON requires sing-box 1.12+; validation uses sing-box 1.13.13 and Xray 1.8.24.
- Existing environment values and database records are retained; setup state is an additive table. Proxy credentials remain shared, quotas remain unenforced and remote configuration delivery remains manual.

### Validation
- 240 Python tests, Ruff, Node 20 production build, shell syntax/ShellCheck and real core configuration checks passed during implementation.
- Browser checks covered onboarding, subscription ownership, anonymous connection pages, themes/languages and a 390px viewport. Real installation, firewall changes, certificate renewal, Telegram delivery and native VPN imports were not exercised.

## [1.0.1] — 2026-07-03

### Fixed
- **Backend crash on boot** — masswidely-broken `from backend.app import X` imports across 9 files reverted to `from app.models import X` (wrong package path post-refactor).
- **Missing `app/core/config_writer.py`** — referenced by bootstrap/protocols API but never existed; protocol auto-sync (xray + sing-box config write + container restart) silently failed on every create/update.
- **Xray ↔ sing-box port collision** — `shadowsocks` was registered in both cores' inbound maps; with `network_mode: host` both tried to bind the same port. Sing-box now owns shadowsocks exclusively.
- **`CREATE TABLE` race across uvicorn workers** — concurrent `init_db()` calls raced on SQLite's non-atomic `checkfirst`; now caught and ignored (harmless — table exists either way).
- **`NodeOut.model_validate(node)` greenlet crash** — pydantic's `from_attributes=True` triggered a lazy-load on the `protocols` relationship outside the async session's greenlet context. Nodes list/create/get now build the response from an explicit field dict.
- **VLESS-Reality was non-functional** — `public_key`/`private_key` defaulted to empty strings; now a real X25519 keypair is generated (same format as `xray x25519`). Auto-provisioned on first boot, no `.env` setup required.
- **sing-box FATAL: `geoip` database removed in 1.12** — route rule migrated to the built-in `ip_is_private` boolean matcher (no external DB).
- **sing-box FATAL: legacy `domain_strategy` deprecated** — set `ENABLE_DEPRECATED_LEGACY_DOMAIN_STRATEGY_OPTIONS=true` pending a proper DNS-section migration.
- **sing-box binding `::` (IPv6 wildcard)** — VPS has no IPv6 uplink; every inbound now binds `0.0.0.0`, matching xray's already-working config.
- **IPv6 literal-destination dials** — client apps hardcoding IPv6 DoT/DNS literals (e.g. Google's `2001:4860:4860::8888`) hung until timeout on a v4-only box; added `{"ip_version": 6, "outbound": "block"}` for an instant reject instead.
- **TLS cert mount path mismatch** — backend mounted `/etc/fvpn/ssl` at `/ssl`, but `settings.CERT_PATH` defaults to `/etc/fvpn/ssl/cert.pem`; Settings page always reported the cert invalid even when it wasn't. Mount target corrected.
- **Dashboard stats mismatch** — page called `/api/stats/dashboard` (flat keys) but rendered the nested shape only `/api/stats/system` returns (RAM/disk/uptime/network). Now fetches and merges both.
- **Dashboard never auto-refreshed** — RAM/disk/node list/events only loaded once on mount; added a 20s poll (WS only ever carried CPU%/active-users/online-nodes).
- **Telegram bot: every command crashed** — `admin_only`/`admin_cb` decorators didn't preserve the wrapped function's signature, so aiogram's DI introspection injected arbitrary context kwargs (`dispatcher`, `bot`, `state`...) into handlers that only accept `msg`. Fixed with `functools.wraps`.
- **`Profile-Title` missing from subscription responses** — clients (Hiddify) fell back to rendering the raw URL/token as the display name. Added `Profile-Title`, `Subscription-Userinfo`, `Profile-Update-Interval` headers.

### Added
- `/cert` Telegram command (status + renew) — parity with the Settings page, previously bot-only had no cert control at all.

### Changed
- Backend: `uvicorn --workers 4` → `--workers 1` (target hardware is 1 vCPU / 1 GB RAM; extra workers only added RAM pressure and were the root cause of the `CREATE TABLE` race).
- `docker-compose.yml`: pinned `sing-box` to `v1.13.13` and excluded both `xray`/`sing-box` from Watchtower's auto-update scope (`com.centurylinklabs.watchtower.enable=false`) — silent `:latest` pulls broke the config schema twice in one week.

### Known limitations (not fixed, by design or scope)
- Protocol credentials are shared per node, not per user — no per-device connection isolation yet.
- Dashboard's 24h traffic chart is illustrative, not real telemetry (no time-series pipeline).
- IP-level whitelist blocking (as opposed to DPI/SNI inspection) can't be bypassed by any client-side protocol config — that requires the node's IP itself to sit inside the allowed range.
