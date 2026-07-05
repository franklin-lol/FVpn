# Changelog

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
