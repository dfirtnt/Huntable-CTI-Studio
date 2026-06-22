# Authentication (Phase A: Boundary & Identity)

This phase establishes a secure startup posture and a verified request identity.
Route authorization (who-can-do-what) and audit logging arrive in later chunks.

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
