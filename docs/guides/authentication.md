# Authentication

This page documents the enterprise boundary now implemented in chunks A-C:
verified request identity, route authorization, and database-backed audit events.

## Modes (`AUTH_MODE`)

| Mode | Use | Production |
|---|---|---|
| `disabled` | Local development. Every request gets a synthetic `local-dev` admin identity. | Rejected at startup unless `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true`. |
| `trusted_header` | An identity-aware proxy injects verified user headers. | Supported. |
| `oidc` | Reserved placeholder. Treated as unauthenticated for now. | Not yet. |

## Fail-closed startup (when `APP_ENV=production`)

Startup aborts if: `AUTH_MODE=disabled` (without the break-glass override),
`TRUSTED_HOSTS` is wildcard, `CORS_ALLOWED_ORIGINS` is wildcard, or CSRF is
active (see below) while `SECRET_KEY` is missing or a known-default/short value.

## Trusted-header contract

The app trusts identity headers **only** when the request carries the proxy
marker (`AUTH_TRUSTED_PROXY_HEADER` == `AUTH_TRUSTED_PROXY_VALUE`) and, if
`AUTH_TRUSTED_PROXY_IPS` is set, originates from a listed peer.

> **The proxy must strip then set.** It must remove any client-supplied
> `X-Huntable-*` headers before injecting verified identity headers, and direct
> network access to the app must be blocked. Application tests prove header
> parsing and spoof rejection; they cannot prove network isolation.

Requests presenting identity headers without the marker (or from an untrusted
peer) are treated as impersonation attempts: ignored and logged.

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
workflow actions, Sigma queue actions, backup/restore, model management,
debugging, and audit APIs require an authenticated identity with the configured
role. Unsafe routes that are not classified fail closed in auth-enabled modes.

Initial roles:

- `viewer`: authenticated reads
- `analyst`: annotation and ingest-oriented analyst actions
- `rule_reviewer`: Sigma queue review actions
- `operator`: workflow/source/scheduled-job operations
- `admin`: settings, credentials, audit, backup/restore, model management, and
  dangerous maintenance

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
- workflow cancellation, bulk cancellation, and stale cleanup
- annotation create and delete
- audit export and retention actions

Authorization denials are recorded best-effort through the central auth
middleware. Non-transactional side effects (Celery dispatch, subprocess restarts,
external PRs) are audited with an explicit status rather than claimed atomic.

Sensitive values are redacted recursively by key name and connection-string
shape. Secret updates record presence/change booleans and hashes, not raw tokens.

> **Not yet mandatory-audited:** backup create/restore, model
> retrain/rollback/version management, observable training, embedding rebuilds,
> evaluation runs, and workflow trigger/retry remain role-gated (and, where
> applicable, CSRF-protected) but their durable audit events are a follow-up.
> These are non-transactional (subprocess/worker/external) paths that need
> status-aware auditing rather than the same-transaction guarantee above.

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
