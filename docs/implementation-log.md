# Implementation log

Plan: docs/implementation-plan.md

## Initial state

- Base: c6bc491; branch: fix/out-of-box-polish. Original tracked files were clean. Existing .serena content is left untouched and ignored.
- Phase 0 confirmed the reported issues by source inspection. bash -n passed for installer, backup and watcher. Docker Engine 29.3.1 provides Linux containers.
- Tests and CI did not exist. Development-only pytest/Ruff are introduced to run the checks requested by the user; no new application dependency is planned.
- Decision: use the current checkout on a dedicated branch. Keep the user's one-commit-per-phase rule; independent workers must not commit.
- Decision: independent installer, backup and core-application changes have disjoint file ownership and can proceed in parallel; integration and review remain sequential.
- Decision: remote nodes receive an honest manual-application result until supported remote delivery exists; they must never restart local cores.

## Progress

- Phase 1: complete; 52 tests, changed-file Ruff, ShellCheck and bash -n passed. Real core checks passed including stdin and empty sets. Commit recorded in Git.
- Phase 2: checks and independent review complete; commit recorded in Git.
- Phase 3: pending.

## Phase 1 evidence and decisions

- Tests exercised real temporary SQLite WAL/snapshots/restoration and transactional config files; subprocess/service boundaries were mocked.
- Python 3.12: 52 tests passed before the final checker-format regression. ShellCheck v0.10.0 and bash -n passed for all three shell files.
- Real Xray 1.8.24 and sing-box 1.13.13 accepted generated configurations for the implemented seven families and empty sets. Xray stdin requires explicit -format json, confirmed by a failing real check then a passing check.
- Review corrected checker compatibility environment, image executable paths, scheduler execution and configured S3 bucket handling.
- Decision: fresh installs seed VLESS Reality and Shadowsocks only. Existing protocol records remain unchanged; optional TLS protocols require deliberate client trust configuration.
- Decision: the checker uses the installed sibling image ID and only its allowlisted compatibility switch. Host binary path variables remain compatible.
- Not tested: real installation, firewall, Certbot renewal, host scheduler or live core restarts. No real environment files or private keys were read.

## Phase 2 evidence and decisions

- JWT validation fails closed without printing the value. Legacy wildcard CORS derives the panel origin, preserving the setting without granting wildcard access.
- Nginx has a fixed trusted IP, overwrites forwarded addresses, and auxiliary host ports bind loopback. Uvicorn does not interpret proxy headers independently.
- Account and IP login limits count pending checks, use bounded memory and monotonic expiry; bcrypt work is bounded and retains permits through cancellation. CPU sampling runs off the event loop.
- Bot authorization is centralized before message/callback/FSM dispatch; a configured bot cannot start with an empty allowlist.
- SSH host keys are persisted atomically as private OpenSSH known-host entries. Changed keys fail before authentication; first contact remains TOFU.
- WireGuard exports fail closed without deleting stored records; ShadowTLS client configuration includes its required Shadowsocks wrapper.
- All runtime image references are pinned by verified digest; Node 20 npm ci and production frontend build passed. nginx -t, synthetic Compose validation, ShellCheck and bash -n passed.
- Final Python 3.12 verification: 177 tests passed; Ruff passed across backend, bot and tests. Existing dependency deprecation warnings remain.
- Independent review identified inherited Nginx request logging and Uvicorn WebSocket query logging. Safe logging now overrides the inherited access format in every server. Sensitive-location Nginx errors omit raw URIs; two real upstream-failure requests retained status/timing without the synthetic token. Uvicorn filters cover real WebSocket hooks and access formatters.
- Not tested: public-network deployment, actual Telegram delivery, production SSH peers or live firewall. No real environment or key files were read.
