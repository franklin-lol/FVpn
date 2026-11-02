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
- Phase 3: complete; checks passed and commit recorded in Git.

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

## Phase 3 evidence and decisions

- Published the 12-line Design Spec before editing UI; docs/ux-contract.md records the additive FastAPI and shared UI contracts.
- Replaced the screens with one restrained Tailwind/CSS-token system: mobile navigation, light/dark/system theme, RU/EN, native focus-managed dialogs, labelled forms and recovery states. Added the missing PostCSS processing configuration without a new dependency.
- Fresh databases receive a singleton setup-state table; existing administrators skip onboarding. The wizard verifies the current password, uses cancellation-safe bcrypt, prevents concurrent password replacement with a conditional update, reuses local credentials and completes only after validated application. Incomplete reused VLESS credentials fail without reseeding.
- The bot retains access after a password change using short-lived standard HS256 tokens signed with the already-shared secret. Standalone password fallback remains available.
- Subscription creation accepts the selected owner with object authorization. Public metadata exposes only token-scoped connection fields and no-store responses. The public guide includes platform/client choice, import/copy fallbacks, QR and three steps.
- Removed random traffic charts/history and unenforced quota controls. Advanced protocol editing and explicit synchronous apply remain available; errors do not claim a successful deployment.
- Confirmed and fixed parent deletion failures with existing child rows; transactional deletion preserves unrelated data and rolls back on failure. Local-node deletion is blocked to prevent leaving live listeners detached from the database.
- Real sing-box client validation exposed obsolete DNS/routing/TUN fields. Generated clients now require sing-box 1.12+ and pass 1.13.13 without compatibility flags. New VMess entries persist one UUID shared by client/server; existing records are untouched.
- Browser evidence: real disposable API/SQLite, first login -> wrong-password recovery -> password change -> local preset -> Users; subscription created through the UI belongs to the selected demo user. Anonymous public metadata has only the five declared fields and no-store. Invalid links have retry/recovery.
- Browser evidence: 390px viewport without horizontal overflow; RU/EN and light/dark switching, QR rendering, import URL, modal focus and Escape checked. Final Login input labels target controls with no duplicate IDs. No public-page console errors observed.
- Final Login Lighthouse snapshot: accessibility 100 and best practices 100; no accessibility findings. This is a single-screen automated check, not a whole-product WCAG certification. Indexing is disabled for the private panel.
- Runtime backend Docker build and Node 20 npm ci/production build passed. Full Python suite: 240 tests passed; Ruff includes backend, bot, tests and tools. Actual Xray 1.8.24 and sing-box 1.13.13 accepted all generated server/client fixtures.
- Scope retained: shared proxy credentials, no enforced quotas/traffic telemetry, manual remote delivery and first-contact SSH trust. The installer, firewall, renewal and host scripts were never executed; real VPN client import/traffic and external Telegram delivery remain unverified.

## Post-release server diagnostics and fixes

- SSH access was explicitly authorized for read-only diagnostics. No server files, configuration, containers or credentials were changed. The local access file was untracked and is now excluded from Git and the root Docker build context, along with the local diagnostic directory.
- Observed Docker 29.1.3 accepts API 1.44 or newer; Watchtower 1.7.1 was repeatedly exiting with its default API 1.25. Its tagged source confirms no API negotiation and no updates for pinned digests. The updater is now opt-in through the `updates` profile with a configurable API default of 1.44; ordinary startup no longer starts it.
- The bot was already polling and serving commands successfully after container recreation. Only presence/count/format of runtime settings were checked, without printing their values. Installer output and documentation now explain that `restart` does not reload an edited env file.
- HTTPS returned 200 with normal certificate verification; backend health and loopback-only auxiliary listeners were confirmed. The two initial protocols are intentional and remain unchanged.
- Direct backend and HTTPS requests both confirmed a 404 for the subscription collection with a trailing slash, while OpenAPI registered only the canonical form. Hidden GET/POST aliases now share the existing handlers and authorization; schema paths remain stable.
- Regression proof: the slash cases failed before the alias fix. Focused tests passed, followed by all 245 Python 3.12 tests and Ruff across backend, bot, tests and tools. Existing dependency deprecation warnings remain.
- Static infrastructure checks passed: bash -n, ShellCheck, Compose default/optional service selection, API 1.44 default and 1.41 override. The installer was not executed. Frontend and proxy configuration generation were unchanged.
- Not tested: applying these fixes to the live server, actual VPN client traffic, certificate renewal or compatibility with old Compose releases. Server changes remain for the operator to apply.
