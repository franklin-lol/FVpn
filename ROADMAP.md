# FVpn roadmap

This is a prioritized backlog, not a list of delivered features or release dates.
The goal is a small personal VPN deployment that is easy to install, understand
and recover. Each stage must ship independently with focused regression checks.

## Current baseline

- One FastAPI/React panel, SQLite persistence and Docker Compose.
- New installations seed VLESS Reality and Shadowsocks. Other implemented
  protocols are added deliberately; their presence in the catalog is not proof
  of compatibility with every client.
- One subscription includes all active nodes and protocols. sing-box/Hiddify
  and Clash exports already contain client-side selection by measured latency.
  This is not server-load balancing or a guarantee of uninterrupted sessions.
- Remote SSH provisioning currently supports Shadowsocks only. Other remote
  configurations are delivered manually. A full panel is not needed per node.
- SQLite backups already verify restoration into a temporary database. Public
  client imports, complete recovery and certificate renewal need real trials.

## P0: prove the complete connection and recovery paths

- [ ] Verify the public guide, app import button, copied subscription and QR in
  current Hiddify and Streisand releases. Record app/OS versions and supported
  protocols. Keep guide links distinct from machine-readable subscriptions.
- [ ] Exercise client selection with two nodes: working, stopped, unreachable
  and UDP-blocked. Check routing, DNS and IPv4/IPv6 behavior as well as latency.
- [ ] Restore SQLite, proxy configuration and TLS onto a disposable server;
  verify startup and an actual client connection. Preserve the original volume.
- [ ] Exercise certificate renewal and a failed renewal without losing the panel.
- [ ] Resolve GitGuardian using the exact reported file/line. Confirm whether it
  is a fixture or an exposed secret; rotate affected real credentials if needed.

Acceptance: a documented install -> import -> connect -> failover -> restore
trial succeeds. Failed actions produce useful errors without exposing secrets.

## P1: connect additional servers safely

- [ ] Extend the existing SSH workflow from Shadowsocks to tested VLESS Reality
  and Hysteria2 presets, with environment/port/TLS checks before changing a node.
- [ ] Validate candidate configurations, preserve the previous working state and
  roll back failed changes. Repeated setup must not duplicate nodes or rotate keys.
- [ ] Add batch setup with bounded concurrency and per-node progress, retry and
  cancellation. Persist job outcomes safely so a panel restart cannot imply success.
- [ ] Show SSH host fingerprints in setup and make existing rejection of changed
  keys understandable without bypassing host verification.

Acceptance: add several independent nodes from one panel; a failed node does not
affect healthy nodes, existing services or the panel's local proxy containers.

## P2: one profile, clear regions and predictable fallback

- [ ] Use the existing node group metadata for client-visible regions.
- [ ] Expose manual region choice, automatic latency selection and an explicit
  fallback policy using client-supported groups. Label format limitations.
- [ ] Make routing modes explicit: all traffic through the selected proxy or
  deliberate split routing. Explain which traffic bypasses the proxy.
- [ ] Check availability through the actual client connection, not just panel
  HTTP reachability. Test new connections after a node failure.

Acceptance: one imported subscription offers regions and automatic selection in
supported clients. Existing TCP sessions may reconnect; do not promise migration
of live sessions or distribution by CPU/load without an implemented mechanism.

## P3: finish useful presets before adding protocol names

- [ ] Keep VLESS Reality as the default TCP option and Shadowsocks as a simple
  alternative; finish Hysteria2 as an independently tested UDP option.
- [ ] Finish Trojan presets with valid TLS, clear domain requirements and
  configuration checks. Keep advanced options available without unsafe defaults.
- [ ] Add TUIC and ShadowTLS convenience presets only after real client tests
  demonstrate a useful alternative to the tested TCP/UDP options.

Acceptance: each recommended preset has a tested client matrix, required ports,
certificate requirements and a reproducible connection check.

## P4: an ordinary proxy when a full VPN is unnecessary

- [ ] Document the client-side HTTP/SOCKS listener and use without system-wide VPN.
- [ ] Add an optional server-side HTTP/SOCKS endpoint with authentication, source
  IP restrictions and bounded connections; do not expose an unauthenticated proxy.
- [ ] Explain credentials, supported applications and safe transport explicitly.

Acceptance: an authorized application can use the proxy; unauthorized access is
rejected. Public proxy access remains opt-in and separate from subscription URLs.

## Delivery constraints

- Keep Python 3.12, FastAPI 0.111, SQLAlchemy 2.0.30, Node 20 and React 18.
- Preserve existing nonempty environment settings and SQLite records. Schema
  changes are additive with safe startup upgrades; dependencies need justification.
- Use the current monolith and SSH path. No new privileged executor, PostgreSQL,
  multiple backend workers or versioned configuration service.
- Per-user protocol credentials, enforced quotas and real traffic telemetry
  remain deferred. Region selection must not be presented as load telemetry.
- Run meaningful pytest/Ruff, Node 20 build, shell static checks and actual core
  configuration validation when relevant. Never run host-management scripts as tests.
- Never publish environment files, access credentials, private keys or backups.

Implementation details and design specs belong in stage-specific plans after
the corresponding stage is selected. This roadmap does not authorize deployment.
