# Authentication

This page documents the enterprise boundary now implemented in chunks A-C:
verified request identity, route authorization, and database-backed audit events.

For step-by-step deployment behind an OAuth proxy (Google / GitHub / Microsoft),
see [Enterprise SSO Setup](enterprise-sso.md).

## Modes (`AUTH_MODE`)

| Mode | Use | Production |
|---|---|---|
| `disabled` | Local development. Every request gets a synthetic `local-dev` admin identity. | Rejected at startup unless `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true`. |
| `trusted_header` | An identity-aware proxy injects verified user headers. | Supported. |
| `oidc` | Reserved placeholder. Treated as unauthenticated for now. | Not yet. |

## Fail-closed startup (when `APP_ENV=production`)

Startup aborts if: `AUTH_MODE=disabled` (without the break-glass override),
`AUTH_MODE=trusted_header` with an empty `AUTH_TRUSTED_PROXY_IPS` (without the
break-glass override below), `TRUSTED_HOSTS` is wildcard, `CORS_ALLOWED_ORIGINS`
is wildcard, or CSRF is active (see below) while `SECRET_KEY` is missing or a
known-default/short value.

## Trusted-header contract

The app trusts identity headers **only** when the request carries the proxy
marker (`AUTH_TRUSTED_PROXY_HEADER` == `AUTH_TRUSTED_PROXY_VALUE`) and, if
`AUTH_TRUSTED_PROXY_IPS` is set, originates from a listed peer.

In production, `AUTH_TRUSTED_PROXY_IPS` is **required** for trusted-header mode:
an empty allowlist would accept identity headers from any direct peer, letting a
client forge admin. Startup fails closed unless
`ALLOW_INSECURE_PRODUCTION_TRUSTED_PROXY_OPEN=true` is set — use that override
only when direct network access to the app is blocked outside the application
(the network-level isolation this contract already assumes).

> **The proxy must strip then set.** It must remove any client-supplied
> `X-Huntable-*` headers before injecting verified identity headers, and direct
> network access to the app must be blocked. Application tests prove header
> parsing and spoof rejection; they cannot prove network isolation.

Requests presenting identity headers without the marker (or from an untrusted
peer) are treated as impersonation attempts: ignored and logged.

Successful authentication is audited at the upstream identity proxy / IdP
boundary, not by Huntable. In `trusted_header` mode the app consumes a verified
identity that has already passed the proxy login flow; it does not own login,
logout, MFA, session refresh, or failed-login events. Preserve the
`X-Request-ID` header in proxy logs so successful proxy-auth events can be
correlated with Huntable authorization denials and application mutation audits.
Forward proxy / IdP logs to the deployment SIEM or append-only log store for
successful-auth evidence.

## Request IDs

Every response carries `X-Request-ID` (echoed from the proxy if provided, else
generated). It is attached to `request.state.request_id` for correlation.

## Route authorization

When auth is enabled, routes are checked against the route manifest after
FastAPI route registration.

Public routes are intentionally minimal:

- `/health`
- `/api/health`
- `/static/*`

Detailed health, capabilities, settings, source mutation, scheduled jobs,
workflow actions, Sigma queue actions, article mutations (delete, bulk-action,
mark-reviewed), backup/restore, model management, debugging, and audit APIs
require an authenticated identity with the configured role. Unsafe routes that
are not classified fail closed in auth-enabled modes, and any unsafe route that
is only authenticated (no role) must be listed in an explicit allowlist
(`AUTHENTICATED_UNSAFE_ALLOWLIST`) or it fails startup and tests.

Initial roles and their group env vars (`_ROLE_ENV` in `src/web/security/config.py`):

- `analyst` (`AUTH_ANALYST_GROUPS`): annotation and ingest-oriented analyst actions
- `rule_reviewer` (`AUTH_REVIEWER_GROUPS` -- note the shortened env var name): Sigma queue review actions
- `operator` (`AUTH_OPERATOR_GROUPS`): workflow/source/scheduled-job operations
- `admin` (`AUTH_ADMIN_GROUPS`): settings, credentials, audit, backup/restore, model management, and
  dangerous maintenance

There is no separate `viewer` role. Routes classified `authenticated` (most
reads) require only a verified identity, not any of the roles above.
`admin` satisfies all role checks.

## CSRF protection

Browser-originated unsafe requests (`POST`/`PUT`/`PATCH`/`DELETE`) require a
signed `X-CSRF-Token` header when CSRF is active.

- `CSRF_ENABLED=auto` (default): active whenever auth is enabled, on the
  assumption the upstream proxy authenticates the browser with cookies.
- `CSRF_ENABLED=true`: always active.
- `CSRF_ENABLED=false`: disabled. Choose this only for a bearer-only/cookieless
  deployment, and document at the proxy why cross-site browser submission is not
  a risk.

Tokens are stateless, HMAC-signed with `SECRET_KEY`, bound to the authenticated
user id, and time-limited. They are rendered into pages via a `csrf-token` meta
tag, and a same-origin `fetch` shim in `base.html` attaches the header
automatically (cross-origin calls such as LMStudio or GitHub are untouched).
Service callers (`actor_type == "service"`) and routes classified
`service_only` are exempt; "missing browser headers" is never a blanket bypass.
CSRF is layered on top of identity and role checks, not a replacement for them.

In local `AUTH_MODE=disabled` development, CSRF is inactive (no token required).

## Audit events

Audit events are stored in the `audit_events` table and include actor, request
ID, action, target, status, source IP, user agent, and redacted metadata.

Mandatory audit means the event is written in the **same transaction** as the
mutation: if the audit write fails, the mutation is rolled back. Current
mandatory-audit coverage:

- settings and secret mutations
- source config mutations (toggle, min content length, image OCR, lookback,
  check frequency) and source collection requests
- scheduled-job config updates
- Sigma queue actions (add, edit/YAML, approve, reject, bulk, delete) and PR
  submission (status-aware: the git/GitHub side effect is recorded with explicit
  success/failure)
- workflow trigger, retry, cancellation, bulk cancellation, and stale cleanup
  (trigger and retry also persist a redacted-safe `initiated_by` snapshot in the
  execution's `config_snapshot` so worker-side attribution can reference the
  originating human; service-originated triggers carry no `initiated_by`)
- annotation create and delete
- audit export and retention actions
- clearing and backfilling subagent eval records (the audit row joins the same
  transaction as the record delete/update)

Authorization denials are recorded best-effort through the central auth
middleware. Non-transactional side effects (Celery dispatch, subprocess restarts,
external PRs) are audited with an explicit status rather than claimed atomic.
Successful authentication is intentionally deferred to the upstream proxy / IdP
audit trail; Huntable records authorization denials and application-side
mutations once a verified identity reaches the app.

### Status-aware audit coverage

Paths whose side effect is a subprocess, a Celery dispatch, or a background
thread cannot offer the same-transaction guarantee: the side effect is not
rollbackable. These record an `attempted` event before the side effect and a
terminal `success` / `failure` event once the outcome is known, via
`AsyncAuditService.record_out_of_band`, which uses its own short-lived session
and is bounded by a timeout so a stalled database costs an audit row rather than
hanging a privileged request. Covered:

- backup create, restore, restore-from-file, and cron schedule add/remove
- model retrain, evaluate, and rollback (retrain and rollback capture the actor
  at the route boundary and hand it to the background thread, so the terminal
  event keeps human attribution)
- bulk embedding rebuild and per-article embedding generation (dispatch only:
  the worker-side outcome is not observable from the route)
- evaluation runs (workflow, subagent, Sigma), eval bundle export, and
  LLM-powered bundle diagnosis
- observable training and observable evaluation runs

One consequence worth knowing: a full-database restore replaces `audit_events`
along with every other table, so the pre-restore `attempted` row does not survive
a *successful* restore -- the post-restore terminal row is what persists. The
attempt row is what remains when a restore fails, times out, or is killed
partway, which is the case where the record matters most.

Sensitive values are redacted recursively by key name, by connection-string
shape, and by value-level scrubbing of embedded credentials (URL `user:pass@`,
`x-access-token:`, `Bearer` headers, and known token prefixes such as `ghp_`,
`github_pat_`, `sk-`, `pk-lf-`) so a secret carried inside a free-text string
(e.g. a git error message) is caught even under an innocuous key name. Secret
updates record presence/change booleans and hashes, not raw tokens.

> **Model version management** (listing and comparing versions) is read-only and
> therefore not audited; the mutating operations on those routes -- retrain,
> evaluate, rollback -- are covered above.

Admin-only audit endpoints:

- `GET /api/audit/events`
- `POST /api/audit/export`
- `DELETE /api/audit/retention`
- `GET /api/audit/health`

`AUDIT_RETENTION_DAYS` defaults to `365`. Retention deletion is explicit and
admin-triggered; it is not an automatic local-development cleanup.

## Tamper-risk boundary

The phase-one audit trail is database-backed. It is durable application data,
but it is not an immutable ledger: a database administrator or someone with
direct database write access can alter or delete rows.

For higher assurance, forward audit exports, database logs, or infrastructure
logs to a SIEM or append-only log store controlled outside the app database.
