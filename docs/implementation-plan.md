# FVpn implementation plan

Approved scope: repair the out-of-box installation, apply minimum security controls, and polish the existing UI for both beginners and experienced operators.

## Constraints

- Preserve Python 3.12, FastAPI 0.111.0, SQLAlchemy 2.0.30, Node 20 and React 18.
- Do not read real environment files, private keys, or deployed proxy configuration.
- Do not execute install.sh or scripts/*.sh. Shell validation is limited to bash -n and ShellCheck.
- Use synthetic environment files, temporary SQLite databases, mocked service control and isolated Linux check containers.
- Preserve nonempty environment values and existing SQLite records. Schema changes must be additive.
- No per-user proxy credentials, enforced traffic quotas, real traffic telemetry, privileged executor, versioned configuration service, PostgreSQL or multiple workers.
- One tested commit per phase; report before advancing. The user approved continuous execution of all phases.

## Phase 1: operational fixes

1. Installer: checkout/env ordering, empty secret handling, private file permissions, SSH/firewall safety, TLS publication/renewal and executable modes.
2. Backup: SQLite backup API, archive verification by isolated restoration, shared API/CLI implementation.
3. Core config application: validate both candidates, serialize application, preserve a single rollback copy, apply empty sets and guard local-node identity.
4. Remote setup: use one set of generated credentials; report unsupported/manual operations honestly.
5. Correct documentation and remove unused Redis from new deployments while retaining existing environment compatibility.

## Phase 2: minimum security

1. Deny-by-default bot access, startup checks, and message/callback/FSM guards.
2. Validate JWT secrets, trust only configured proxy peers, bounded account/IP lockout, loopback auxiliary ports, domain-based CORS.
3. Persistent SSH TOFU, disable WireGuard client exports, offload blocking CPU/password work.
4. Frontend lockfile and tested pinned images without changing the declared stack.

## Phase 3: UX

Publish the Design Spec before editing UI. Add authenticated onboarding, a public token-scoped connection page, correct subscription ownership, RU/EN, light/dark themes, mobile layouts and actionable states. Remove illustrative traffic. Preserve advanced protocol configuration behind an explicit disclosure.

## Verification

Python 3.12: focused pytest plus Ruff. Node 20: npm ci and production build. Shell: bash -n and ShellCheck only. Core binaries: validate synthetic generated configs without host networking, Docker socket, real certificates or application data. Review each phase before its commit.

