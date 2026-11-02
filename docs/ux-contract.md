# Phase 3 UX contract

The existing FastAPI OpenAPI document remains the schema authority. Existing routes and omitted request fields retain their previous behavior. No runtime dependency or stack version change is required.

## Authenticated setup

- `GET /api/setup` (active administrator) returns `required`, `password_changed`, `local_node_id`, `recommended_ready` and `nodes` (`id`, `name`, `host`, `local`).
- `POST /api/auth/password` (current user) accepts `current_password` and `new_password`, verifies the current hash off-loop, and returns `{"status":"password_changed"}`. New passwords require 12 characters and at most 72 UTF-8 bytes. Existing login passwords remain compatible.
- `POST /api/setup/complete` (administrator) accepts `node_id` and `preset` (`recommended` or `existing`). Reuses the chosen local node and existing credentials; recommended ensures a VLESS Reality TCP preset only when absent and validates/applies local configuration. Remote delivery remains explicitly manual. Returns `{"status":"configured"}` only after successful local apply (or explicit existing/manual selection). Errors preserve pending setup for retry.
- A singleton additive setup-state table marks fresh databases pending. Existing administrators without state are considered configured. Password-change state survives restart. The wizard never overwrites environment secrets or reseeds existing credentials.
- The bot must retain API access after changing the administrator password: short-lived HS256 bearer tokens signed with its already-shared JWT_SECRET may replace password login when available, retaining the legacy password fallback. All API authorization still consults the current active account in SQLite.

## Subscriptions

- Existing `POST /api/subscriptions` accepts optional positive `user_id`. Omitted means current user; only administrators may select another existing user.
- `GET /api/subscriptions/info/{token}` is public and token-scoped. Returns only `format`, `url`, `connect_url`, `expires_at` and `available_formats`. It checks the same owner enabled/expiry conditions as fetch. No username, protocol secrets, SSH material or server configuration is exposed.
- `SubOut` gains additive `connect_url` pointing to `/s/{token}`. Fetch format may be switched among supported client formats; tokens remain secret bearer links. Public metadata and downloaded configurations use no-store headers.
- Public UI loads metadata without administrator authorization, offers Hiddify and v2rayNG import links with copy fallback, formats appropriate for the selected client, and a QR of the current import URL. A token is never stored in persistent frontend preferences.
- Empty protocol support remains actionable. Errors use the existing FastAPI `detail` contract: 401 authentication, 403 authorization/disabled, 404 missing, 409 unsupported/manual/apply failure, 422 invalid input.

## UI integration

- React 18 SPA; existing Axios/Zustand/Tailwind mechanisms. No new application dependencies.
- Shared `useI18n()` returns `t(russian, english)` and `language`; preferences persist theme/language only. Components import from `components/ui.jsx`: Button, Card, PageHeader, Field, Modal, Badge, Loading, ErrorState, EmptyState, CopyButton.
- Button supports `variant` (`primary`, `secondary`, `danger`, `ghost`), `loading`, `icon`, ordinary button attributes. Field wraps a labelled control and supports `hint`. Modal uses native dialog for keyboard focus/escape. API errors use `apiError(error)` from utils/api.
- Root owns layout, tokens, shared components, router, login, overview, users, setup and public connection pages. The frontend worker owns Nodes, Protocols and Settings pages only.
- Every remote screen has loading/error/retry and empty/next-action behavior. Mutations disable repeated submission. Server results remain authoritative; no fabricated traffic or telemetry.
