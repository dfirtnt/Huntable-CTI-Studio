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
`TRUSTED_HOSTS` is wildcard, or `CORS_ALLOWED_ORIGINS` is wildcard.

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

## Audit events

Audit events are stored in the `audit_events` table and include actor, request
ID, action, target, status, source IP, user agent, and redacted metadata.

Current audit coverage includes:

- authorization denials through the central auth middleware
- settings and secret mutations with mandatory same-transaction audit writes
- audit export and retention actions

Sensitive values are redacted. Secret updates record presence/change metadata
and hashes, not raw tokens.

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
