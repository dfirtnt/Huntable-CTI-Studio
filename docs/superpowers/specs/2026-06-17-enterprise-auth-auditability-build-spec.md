# Build Spec: Enterprise Authentication and Auditability

- **Date:** 2026-06-17
- **Status:** Draft build spec
- **Topic:** Make Huntable CTI Studio deployable behind enterprise identity controls with durable audit trails
- **Owner:** TBD

## Plan Decomposition

This build spec is too large for a single plan. It is split into three
independently-shippable, plan-sized chunks (build order A → B → C):

- **Chunk A — Secure Boundary & Request Identity:**
  [`2026-06-17-enterprise-auth-chunk-a-boundary-identity.md`](2026-06-17-enterprise-auth-chunk-a-boundary-identity.md)
  (Slices 1–2)
- **Chunk B — Route Authorization (manifest, deny-by-default, roles, CSRF):**
  [`2026-06-17-enterprise-auth-chunk-b-route-authorization.md`](2026-06-17-enterprise-auth-chunk-b-route-authorization.md)
  (Slice 3 + Slice 6 + the deferred `SECRET_KEY` check)
- **Chunk C — Audit & Accountability:**
  [`2026-06-17-enterprise-auth-chunk-c-audit-accountability.md`](2026-06-17-enterprise-auth-chunk-c-audit-accountability.md)
  (Slices 4–5 + audit access/retention + service identity)

The slice numbering below remains the canonical reference; each chunk spec maps
itself back to these slices.

## Problem

Huntable CTI Studio is currently documented as not safe for hostile networks and
is optimized for local or trusted-lab use. The FastAPI app exposes browser pages,
state-changing APIs, scheduled-job controls, workflow execution, source
configuration, model/provider settings, stored API tokens, Sigma rule review, and
GitHub PR submission without a first-class application identity or audit model.

Enterprise users need to answer:

- Who performed this action?
- What changed?
- When did it happen?
- From where?
- Did it succeed or fail?
- Can direct access bypass SSO?
- Can production accidentally run with auth disabled?

This spec adds the minimum security boundary required for enterprise deployment
without turning the app into a custom identity provider.

## Goals

- Support enterprise SSO through a reverse proxy or identity-aware edge.
- Fail closed in production when authentication or host/CORS hardening is unsafe.
- Establish a request identity context that all routes and audit code can use.
- Protect state-changing routes with deny-by-default behavior when auth is enabled.
- Add role/permission checks for high-risk operations.
- Add durable audit events for security-relevant and data-changing actions.
- Preserve local development behavior through an explicit non-production mode.
- Avoid storing or logging secrets in audit records.

## Non-goals

- No native password database, login page, password reset, or MFA implementation.
- No customer-facing multi-tenancy in this phase.
- No SCIM provisioning in this phase.
- No signed or externally immutable audit ledger in this phase.
- No redesign of existing pages.
- No migration of all app data to per-user ownership.

## Existing Repo Signals

Runtime and contract sources:

- `src/web/modern_main.py` wires the FastAPI app, CORS, trusted hosts, static files,
  and route registration.
- `src/web/routes/__init__.py` is the route surface.
- `src/database/models.py` owns ORM table contracts.
- `run_tests.py` is the canonical test entrypoint.
- `README.md` currently warns not to deploy in hostile networks.

Current security-relevant behavior:

- CORS allows all origins.
- Trusted hosts allows all hosts.
- There is no global authenticated request identity.
- Existing tests intentionally prevent explicit auth dependencies on some source
  endpoints because the current Settings UI sends no API key.
- Provider and GitHub credentials are stored through app settings flows and must
  never appear in audit diffs.

## Deployment Model

The first enterprise-ready version uses one customer per deployment.

Identity is provided by an upstream enterprise control plane:

- Cloudflare Access
- Tailscale Access
- OAuth2 Proxy
- Authentik
- Okta / Entra ID through an OIDC-aware proxy
- Equivalent identity-aware reverse proxy

The app consumes trusted identity headers from that proxy. The app must never
trust these headers unless direct network access to FastAPI is blocked.

## Authentication Modes

Add `AUTH_MODE`:

| Mode | Purpose | Production allowed |
|---|---|---|
| `disabled` | Local development only | No, unless explicit break-glass is set |
| `trusted_header` | Identity-aware proxy passes verified user headers | Yes |
| `oidc` | Reserved for future direct OIDC validation | No-op placeholder in this build |

Required production behavior:

- If `APP_ENV=production` and `AUTH_MODE=disabled`, startup fails.
- If `APP_ENV=production` and `SECRET_KEY` is missing/default, startup fails.
- If `APP_ENV=production` and trusted hosts are wildcard, startup fails.
- If `APP_ENV=production` and CORS origins are wildcard, startup fails.
- A break-glass override may exist, but it must be loud and explicit:
  `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true`.

## Trusted Header Contract

For `AUTH_MODE=trusted_header`, add config:

- `AUTH_TRUSTED_PROXY_HEADER`
- `AUTH_TRUSTED_PROXY_VALUE`
- `AUTH_TRUSTED_PROXY_IPS`
- `AUTH_USER_ID_HEADER`
- `AUTH_EMAIL_HEADER`
- `AUTH_NAME_HEADER`
- `AUTH_GROUPS_HEADER`
- `AUTH_ADMIN_GROUPS`
- `AUTH_ANALYST_GROUPS`
- `AUTH_REVIEWER_GROUPS`
- `AUTH_OPERATOR_GROUPS`

Minimum default header names:

- `X-Huntable-Verified: true`
- `X-Huntable-User-Id`
- `X-Huntable-Email`
- `X-Huntable-Name`
- `X-Huntable-Groups`

Security requirement:

- If `AUTH_MODE=trusted_header`, requests missing the trusted proxy marker are
  unauthenticated even if user/email/group headers are present.
- The upstream proxy must strip all incoming client-supplied `X-Huntable-*`
  headers before it injects verified identity headers. The required proxy
  behavior is **strip then set**, never pass-through then append.
- The app must optionally validate the immediate peer against
  `AUTH_TRUSTED_PROXY_IPS` before accepting trusted identity headers. In
  production trusted-header mode, either `AUTH_TRUSTED_PROXY_IPS` must be set or
  deployment docs must show an equivalent network-level direct-access block.
- If a request contains identity headers but fails the trusted proxy marker or
  trusted proxy source check, treat it as an impersonation attempt: reject it,
  log it, and audit `auth.request_denied` when audit storage is available.
- Documentation must state that direct FastAPI access must be blocked by network
  policy, firewall rules, Docker binding, ingress policy, or equivalent control.
- Documentation must include concrete proxy examples that strip client headers
  before setting identity headers.
- Application tests can prove header parsing, spoof rejection, and trusted peer
  checks, but cannot prove network isolation. Deployment docs must call this out
  explicitly.

## Request Identity

Add a small identity module, for example:

- `src/web/security/identity.py`
- `src/web/security/middleware.py`
- `src/web/security/permissions.py`

Request identity shape:

```python
class RequestIdentity:
    is_authenticated: bool
    user_id: str | None
    email: str | None
    display_name: str | None
    groups: tuple[str, ...]
    roles: tuple[str, ...]
    auth_mode: str
```

The middleware attaches identity to:

- `request.state.identity`
- structured request logs
- audit events

Unauthenticated local/dev requests in `AUTH_MODE=disabled` get a synthetic
identity:

- `user_id="local-dev"`
- `email=None`
- `roles=("admin",)`
- `auth_mode="disabled"`

This keeps the current local workflow intact while making the bypass explicit.

## Roles

Initial roles:

| Role | Capabilities |
|---|---|
| `viewer` | Read pages, read articles, read executions, read metrics |
| `analyst` | Create annotations, trigger normal analysis actions |
| `rule_reviewer` | Edit, approve, reject, validate, enrich, and compare Sigma queue items |
| `operator` | Run source collection, retry/cancel workflows, manage scheduled jobs |
| `admin` | Settings, credentials, source config, auth config, dangerous maintenance |

`admin` includes all roles. Other role inheritance should stay explicit.

Group-to-role mapping is configured through env vars. Do not hardcode customer
group names.

## Permission Model

Use route dependencies for sensitive route groups and middleware for broad
deny-by-default behavior.

Add helpers:

- `require_authenticated`
- `require_role("admin")`
- `require_any_role("operator", "admin")`
- `require_permission("sigma_queue.approve")` only if role checks become too coarse

Global behavior when auth is enabled:

- `GET`, `HEAD`, and `OPTIONS` require an authenticated identity except public
  health/static allowlist entries.
- Unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) require authenticated identity
  and must pass either an explicit permission dependency or an allowlisted route
  classification.

Public allowlist:

- `/health`
- `/api/health`
- `/static/*`
- one minimal readiness endpoint if Docker/Kubernetes needs a separate path

Do not allow `/docs` and `/openapi.json` publicly in production unless explicitly
configured.

Do not publicly allow wildcard health paths. Detailed health and diagnostics
routes must require `operator` or `admin` because current health routes expose
database counts, deduplication details, corruption examples, Redis/Celery state,
model names, external service status, ingestion analytics, and other internal
deployment details.

## Route Protection Targets

Protect these first:

| Area | Minimum role |
|---|---|
| Settings changes | `admin` |
| API key/provider credential changes | `admin` |
| Source add/update/toggle/collect | `operator` or `admin` |
| Scheduled jobs / cron replacement | `operator` or `admin` |
| Workflow trigger/retry/cancel/stale cleanup | `operator` or `admin` |
| Sigma queue edit/approve/reject/bulk/enrich/validate/PR submit | `rule_reviewer` or `admin` |
| Annotation create/delete | `analyst` or `admin` |
| Backup create/download/restore/delete | `admin` |
| Model retrain/rollback/delete/version management | `admin` |
| Embedding rebuild/update jobs | `operator` or `admin` |
| Scrape URL / PDF upload / ingest-triggering uploads | `analyst`, `operator`, or `admin` |
| Evaluation runs/backfills/diagnostics | `operator` or `admin` |
| Observable training and training-data mutation | `admin` |
| AI action endpoints that invoke providers or mutate state | role matching the action; default `operator` or `admin` |
| Semantic search | authenticated; elevate later if needed |
| Export/download actions | authenticated; elevate to `analyst` if content exfiltration risk requires it |
| Detailed health/diagnostics | `operator` or `admin` |
| Debug routes | `admin` |

Any endpoint that mutates state and is not classified should return 403 when
auth is enabled. This is the guardrail against missed route coverage.

Add a generated route manifest before applying route-level roles. The manifest
must enumerate every registered route from `src/web/routes/__init__.py` with:

- path
- methods
- route module
- endpoint name
- public/authenticated/role classification
- audit requirement: `none`, `best_effort`, or `mandatory`
- CSRF requirement for unsafe browser routes

Route classification is enforced in both tests and startup:

- Tests fail if any unsafe method lacks a classification.
- Production startup fails if any unsafe method is unclassified.
- Development may log unclassified routes only while `AUTH_MODE=disabled`, but
  auth-enabled development should use the same fail-closed behavior as
  production.

## CSRF

If the enterprise proxy authenticates the browser with cookies, add CSRF
protection for unsafe methods.

Minimum phase-one approach:

- Generate a signed CSRF token per session/request context.
- Render it into base templates as a meta tag or JS variable.
- Require `X-CSRF-Token` for unsafe browser-originated requests.
- Exempt non-browser service-token routes only if they use explicit bearer or
  internal auth.

If all deployed auth is bearer-header based and cookies are not used, document
why CSRF is not active. Do not leave the decision implicit.

## Service and Worker Identity

Background jobs, scheduler tasks, and CLI calls must not bypass auditability.

Use synthetic service identities:

- `service:celery-worker`
- `service:workflow-worker`
- `service:scheduler`
- `service:cli`

For HTTP calls from internal services, use an internal token or trusted internal
network path with an explicit service identity header. Do not reuse human trusted
headers for service calls.

Audit events created inside worker code should carry the service identity and,
when available, the initiating human request identity copied into the workflow or
task metadata.

## Audit Event Model

Add `AuditEventTable` to `src/database/models.py`.

Suggested fields:

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `created_at` | DateTime | Server-side timestamp |
| `request_id` | String | Correlates logs and audit |
| `actor_type` | String | `human`, `service`, `local-dev`, `unknown` |
| `actor_id` | String | Stable ID from IdP or service identity |
| `actor_email` | String nullable | Human email when available |
| `actor_roles` | JSON | Roles at time of action |
| `source_ip` | String nullable | Proxy-aware client IP |
| `user_agent` | Text nullable | Browser or client |
| `action` | String | Stable action name |
| `target_type` | String nullable | `source`, `workflow_execution`, `sigma_rule`, etc. |
| `target_id` | String nullable | ID as text |
| `status` | String | `success`, `failure`, `denied` |
| `summary` | Text | Human-readable short summary |
| `metadata` | JSONB | Redacted structured data |
| `before_hash` | String nullable | Hash of redacted before snapshot |
| `after_hash` | String nullable | Hash of redacted after snapshot |
| `error_code` | String nullable | Stable failure code |

Indexes:

- `created_at`
- `actor_id`
- `action`
- `target_type`, `target_id`
- `request_id`

## Audit Actions

Initial stable action names:

- `auth.request_authenticated`
- `auth.request_denied`
- `settings.updated`
- `settings.secret_updated`
- `source.updated`
- `source.toggled`
- `source.collection_requested`
- `scheduled_jobs.updated`
- `workflow.triggered`
- `workflow.retried`
- `workflow.cancelled`
- `workflow.stale_cleanup_requested`
- `sigma_queue.rule_edited`
- `sigma_queue.rule_approved`
- `sigma_queue.rule_rejected`
- `sigma_queue.bulk_action`
- `sigma_queue.rule_enriched`
- `sigma_queue.rule_validated`
- `sigma_queue.pr_submitted`
- `annotation.created`
- `annotation.deleted`
- `export.created`
- `debug.action_invoked`

Audit every permission denial for unsafe methods.

## Redaction Rules

Never write these to audit metadata:

- API keys
- GitHub tokens
- provider credentials
- passwords
- Redis/Postgres connection strings
- session cookies
- Authorization headers
- raw provider request/response payloads

Potentially sensitive but allowed in summarized form:

- prompt names and versions
- model names
- source IDs and URLs
- article IDs and titles
- Sigma rule IDs and title
- workflow execution IDs

For large or sensitive objects, store:

- changed field names
- old/new presence booleans for secrets
- SHA-256 hashes of redacted snapshots
- compact summaries instead of full bodies

Example for secret update:

```json
{
  "key": "WORKFLOW_OPENAI_API_KEY",
  "old_present": true,
  "new_present": true,
  "secret_changed": true
}
```

## Audit Reliability

For high-risk mutations, audit is mandatory. If the audit event cannot be written,
the mutation must fail before commit.

Mandatory-audit actions:

- settings changes
- secret changes
- source config changes
- scheduled job changes
- Sigma approve/reject/bulk/PR submit
- workflow cancellation/cleanup
- debug actions

Best-effort audit is acceptable for:

- read-only access events
- routine page views
- low-risk exports if the export itself is otherwise logged

Mandatory audit must use a concrete transaction API, not ad hoc route code:

- Add `AuditService.record_mandatory(session, event)` for synchronous routes and
  `AsyncAuditService.record_mandatory(session, event)` for async routes.
- Route code that mutates state and requires mandatory audit must use a shared
  transaction boundary that commits the mutation and audit event together.
- If a legacy route currently opens and commits inside a service, refactor that
  service to accept an existing session before marking the route enterprise-ready.
- Do not implement mandatory audit as "commit mutation, then try to audit" for
  the high-risk actions listed above.
- If transaction sharing is impossible for a specific route, classify that route
  as not enterprise-ready and keep it denied in auth-enabled production until it
  is refactored.

Audit table creation is not best-effort:

- `audit_events` table and indexes must be part of the required schema creation
  path.
- Startup must fail in production if the audit table or required indexes are
  missing.
- Best-effort DDL skips are not acceptable for mandatory-audit infrastructure.

Detailed health should expose audit readiness only to `operator` or `admin`.

## Audit Access, Retention, and Tamper Risk

Phase one audit storage is database-backed and mutable by database
administrators. This is acceptable only if the docs state the tamper risk
plainly and do not oversell the audit log as immutable.

Add operational controls:

- Read access to audit events requires `admin` by default.
- `operator` may view health/audit readiness, not full audit contents, unless a
  separate read-only audit role is added.
- Audit export requires `admin` and emits its own `audit.exported` event.
- Audit retention is configurable by `AUDIT_RETENTION_DAYS`; default `365`.
- Retention deletion requires `admin`, is never automatic in local development,
  and emits `audit.retention_applied`.
- Documentation must describe database-level tamper risk and recommend shipping
  audit exports or database logs to an external SIEM/log store for higher
  assurance.

## Request IDs and Logging

Add request ID middleware:

- Accept `X-Request-ID` from trusted proxy if present.
- Otherwise generate a UUID.
- Return it as `X-Request-ID`.
- Include it in structured logs and audit events.

Do not log raw request bodies globally. Route-specific logs must use the same
redaction helpers as audit.

## Configuration

Add environment variables:

```bash
APP_ENV=development
AUTH_MODE=disabled
ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=false

TRUSTED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:8001

AUTH_TRUSTED_PROXY_HEADER=X-Huntable-Verified
AUTH_TRUSTED_PROXY_VALUE=true
AUTH_TRUSTED_PROXY_IPS=
AUTH_USER_ID_HEADER=X-Huntable-User-Id
AUTH_EMAIL_HEADER=X-Huntable-Email
AUTH_NAME_HEADER=X-Huntable-Name
AUTH_GROUPS_HEADER=X-Huntable-Groups
AUTH_ADMIN_GROUPS=
AUTH_ANALYST_GROUPS=
AUTH_REVIEWER_GROUPS=
AUTH_OPERATOR_GROUPS=

AUDIT_RETENTION_DAYS=365
CSRF_ENABLED=auto
```

Update `.env.example` with safe commented examples. Do not add real customer
group names.

## Implementation Slices

### Slice 1: Production hardening config

Files likely touched:

- `src/web/modern_main.py`
- `src/web/security/config.py`
- `.env.example`
- docs deployment/auth guide
- tests for startup config validation

Build:

- Parse trusted hosts and CORS origins from env.
- Replace wildcard defaults in production.
- Add startup fail-closed checks.
- Preserve current local defaults for development.

Acceptance:

- Production with `AUTH_MODE=disabled` fails startup.
- Production with wildcard trusted hosts fails startup.
- Production with wildcard CORS fails startup.
- Development still starts with current local workflow.

### Slice 2: Identity and request ID middleware

Files likely touched:

- `src/web/modern_main.py`
- `src/web/security/identity.py`
- `src/web/security/middleware.py`
- tests under `tests/api/` or `tests/unit/`

Build:

- Add request ID middleware.
- Add trusted-header identity parsing.
- Reject spoofed identity headers unless the proxy marker and trusted proxy
  source checks pass.
- Add synthetic local-dev identity for disabled mode.
- Attach identity to `request.state.identity`.

Acceptance:

- Missing trusted proxy marker means unauthenticated in `trusted_header` mode.
- Forged user headers without marker are ignored.
- Forged user headers from an untrusted peer are rejected even if the marker is
  present.
- Tests assert the proxy contract requires strip-then-set behavior in docs and
  spoof rejection in code.
- Valid trusted headers produce expected roles.
- Every response has `X-Request-ID`.

### Slice 3: Route manifest, global auth guard, and permission helpers

Files likely touched:

- `src/web/security/permissions.py`
- `src/web/security/route_manifest.py`
- `src/web/routes/*.py` for sensitive route dependencies
- route registration or middleware wiring
- tests for representative route groups

Build:

- Add public allowlist.
- Generate and maintain route classification metadata for every registered route.
- Require identity for all non-public routes when auth is enabled.
- Deny unsafe methods without explicit route classification or permission.
- Add role dependencies to high-risk routes.

Acceptance:

- Public health still works unauthenticated.
- Detailed health endpoints require `operator` or `admin`.
- Static assets still work unauthenticated if required by login/proxy UX.
- Unsafe unclassified routes fail tests and fail production startup.
- Backup/restore, model retrain/rollback, embeddings update, scrape/PDF upload,
  eval runs/backfills/diagnostics, observable training, AI action endpoints, and
  semantic search have explicit classifications.
- Settings mutations require `admin`.
- Sigma approval requires `rule_reviewer` or `admin`.
- Workflow retry/cancel requires `operator` or `admin`.

### Slice 4: Audit table and service

Files likely touched:

- `src/database/models.py`
- migration/bootstrap path used by `create_tables`
- `src/services/audit_service.py`
- tests for redaction and audit writes

Build:

- Add `AuditEventTable`.
- Add audit service with redaction helpers.
- Add action constants.
- Add mandatory-audit helpers that require a caller-owned transaction.
- Add production startup validation for audit table and required indexes.

Acceptance:

- Audit table is created in new installs.
- Production startup fails if required audit schema objects are missing.
- Redaction removes secrets from nested metadata.
- Mandatory audit write failure rolls back the selected mutation.
- Audit records include actor, request ID, action, target, status, and redacted metadata.

### Slice 5: Audit high-risk mutations

Files likely touched:

- settings routes
- sources routes
- workflow routes
- scheduled jobs routes
- sigma queue routes
- annotations routes
- export/debug routes as needed

Build:

- Add audit calls to all initial high-risk route targets.
- Use compact summaries and redacted metadata.
- Include workflow execution ID or Sigma queue ID where applicable.

Acceptance:

- Each listed action emits one success/failure/denied audit event.
- Secret changes audit presence/change only.
- Bulk actions summarize counts and target IDs, not full payloads.
- Tests cover at least one success and one denied path per route family.

### Slice 6: CSRF decision and browser integration

Files likely touched:

- base templates or common JS
- security middleware/dependency
- frontend fetch helpers
- tests for unsafe browser requests

Build:

- If cookie-backed auth is used, add CSRF token issue and validation.
- If bearer-only auth is chosen, document why CSRF is disabled.

Acceptance:

- Unsafe browser requests without CSRF token fail when CSRF is enabled.
- Existing UI flows include the token automatically.
- Non-browser service routes use explicit service identity, not CSRF bypass by accident.

### Slice 7: Documentation and operator runbook

Files likely touched:

- `README.md`
- `docs/guides/authentication.md`
- `docs/deployment/technical-readout.md` or new deployment security guide
- `.env.example`

Build:

- Document supported deployment topologies.
- Document direct-access blocking requirement for trusted headers.
- Document strip-then-set proxy header behavior with concrete examples.
- Document roles and group mapping.
- Document audit event retention/export expectations.
- Document audit tamper risk and recommended external SIEM/log export.
- Replace or qualify the hostile-network warning once controls are implemented.

Acceptance:

- A new operator can configure trusted-header SSO from docs.
- Docs explicitly say what the app does and does not guarantee.
- Docs include a production checklist.

## Testing Plan

Use `python3 run_tests.py` unless a narrower direct test is clearly docs-only.

Minimum checks by slice:

| Slice | Verification |
|---|---|
| Config hardening | targeted unit/API tests plus `python3 run_tests.py smoke` |
| Identity middleware | targeted unit/API tests |
| Permission guards | `python3 run_tests.py api` or focused API tests through `run_tests.py --paths` |
| Audit service/model | targeted unit/integration tests |
| Route audit coverage | targeted API tests per route family |
| CSRF/UI fetch changes | `python3 run_tests.py ui` or focused Playwright where affected |
| Docs-only updates | docs build test or MkDocs build |

Regression tests to add:

- Production fails when auth is disabled.
- Production fails with wildcard CORS/trusted hosts.
- Trusted-header auth rejects forged user headers without proxy marker.
- Trusted-header auth rejects forged identity headers from untrusted peers.
- Role mapping from groups is deterministic.
- Route manifest test fails if any unsafe route is unclassified.
- Production startup fails if any unsafe route is unclassified.
- Detailed health endpoints require `operator` or `admin`.
- Settings secret update audits redacted metadata only.
- Sigma approval emits audit with actor and target.
- Workflow retry carries actor into execution/task metadata where applicable.
- Audit write failure blocks mandatory-audit mutation.
- Audit schema validation fails production startup when table/indexes are missing.
- Audit export and retention actions require `admin` and emit audit events.

## Migration and Backward Compatibility

- Existing local users keep `AUTH_MODE=disabled` by default in development.
- Existing production-like deployments must set explicit auth and host/CORS config.
- New `audit_events` table is additive.
- No existing user table migration is required.
- Existing tests that assert no explicit route auth guards should be updated to
  reflect the new global auth model and local-dev disabled mode.

## Security Review Checklist

- Direct FastAPI access cannot spoof trusted headers in the documented deployment.
- Proxy docs require client identity headers to be stripped before verified
  identity headers are set.
- Trusted proxy source validation or equivalent direct-access block is configured.
- Production cannot silently start with auth disabled.
- Wildcard hosts and CORS are blocked in production.
- All unsafe routes are route-manifest classified and either explicitly protected
  or explicitly denied.
- Detailed health routes are not publicly exposed.
- Secrets are never logged or audited.
- Audit failure blocks high-risk mutations.
- Audit table and indexes are required schema, not best-effort DDL.
- Audit read/export/retention permissions are defined.
- Audit tamper risk is documented.
- Service identities are distinct from human identities.
- CSRF posture is explicit and tested.
- `/docs` and `/openapi.json` are not public in production unless intentionally enabled.

## Security Review Findings

### SRF-1: production trusted_header with empty proxy allowlist is not fail-closed

- **Surfaced:** v7.5.0 release security review, 2026-06-22.
- **Status:** OPEN. Remediation deliberately deferred by operator decision in
  this review session; this note records the finding so it is actioned before
  v7.5.0 ships. No code or tests changed yet.
- **Severity:** High (privilege escalation to `admin`). LIVE, not latent, on
  the `enterprise-auth-audit` branch.

**Gap.** The "Trusted Header Contract" section above requires that in production
trusted-header mode, either `AUTH_TRUSTED_PROXY_IPS` is set or deployment docs
show an equivalent network-level direct-access block. The implementation does
not enforce the config half of that requirement:

- `src/web/security/config.py` `_validate()` rejects production +
  `AUTH_MODE=disabled`, wildcard `TRUSTED_HOSTS`, and wildcard
  `CORS_ALLOWED_ORIGINS`, but does NOT require `AUTH_TRUSTED_PROXY_IPS` when
  `auth_mode` is `TRUSTED_HEADER`. A production deploy with an empty allowlist
  starts cleanly.
- `src/web/security/identity.py` `parse_trusted_identity()` computes
  `peer_ok = (not cfg.trusted_proxy_ips) or (peer_ip in cfg.trusted_proxy_ips)`,
  so an empty allowlist makes every peer trusted. (This matches the "app must
  optionally validate the immediate peer" wording in the contract, which is why
  the gate belongs at the config layer.)

**Impact.** With `AUTH_MODE=trusted_header` and an empty `AUTH_TRUSTED_PROXY_IPS`,
any direct client can forge `X-Huntable-Verified: true` + `X-Huntable-User-Id`
+ `X-Huntable-Groups` and obtain mapped roles (including `admin` via
`map_groups_to_roles`). This is not gated to a future chunk: `AuthorizationMiddleware`
is already registered in `src/web/modern_main.py` and enforces roles from
`request.state.identity`, so the escalation path is exploitable on this branch
today (modulo a deployment that blocks direct FastAPI access by network policy).

**Recommended remediation.**

- Required: make `_validate()` fail closed when `is_production` and
  `auth_mode is TRUSTED_HEADER` and `trusted_proxy_ips` is empty, unless an
  explicit, documented break-glass override env is set (mirror the existing
  `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED` convention, e.g.
  `ALLOW_INSECURE_PRODUCTION_TRUSTED_PROXY_OPEN`). Update
  `tests/unit/test_security_config.py::test_production_trusted_header_ok` to set
  a proxy IP, and add a test asserting production + trusted_header + empty proxy
  IPs fails startup.
- Optional (defense-in-depth, NOT decided here): tighten `identity.py` so an
  empty allowlist denies the peer gate rather than allowing it. Note this
  contradicts the "optionally validate the immediate peer" wording in the
  Trusted Header Contract and changes behavior in three existing Chunk A tests
  (`test_request_identity.py::test_parse_with_marker_authenticates_and_maps_roles`,
  `test_request_identity.py::test_parse_with_marker_but_no_user_id_is_not_authenticated`,
  `test_security_middleware.py::test_trusted_header_mode_authenticates_via_marker_and_groups`),
  and makes dev/test trusted-header usage require `AUTH_TRUSTED_PROXY_IPS` or it
  rejects all requests. Decide config-only vs. config + identity before
  implementing.

## Open Questions

- Which enterprise proxy should be the first documented reference deployment?
- Should API clients use bearer tokens in phase one, or stay unsupported until the
  browser SSO path is complete?
- Should `viewer` be allowed to export/download, or should exports require
  `analyst` because they can move CTI data out of the system?
- Should debug routes be disabled entirely in production instead of admin-only?
- Should detailed health be `operator` or `admin`? Default in this spec is
  `operator` or `admin`.
- Should backup download and backup restore split into separate permissions?
  Default in this spec is `admin` for both.

## Recommended Build Order

1. Production fail-closed config.
2. Request ID and identity middleware.
3. Route manifest generation and unsafe-route classification.
4. Global auth guard with narrow public allowlist.
5. Role dependencies on high-risk route groups.
6. Audit table/service/redaction with required schema validation.
7. Mandatory audit transaction refactors for high-risk mutations.
8. Audit access/export/retention operations.
9. CSRF decision and implementation.
10. Deployment docs and production checklist.

## Definition Of Done

- App can run locally with `AUTH_MODE=disabled` and no behavior regression.
- App refuses insecure production startup by default.
- App can run behind a trusted-header SSO proxy.
- Trusted-header mode rejects spoofed headers unless the request comes through
  the trusted proxy contract.
- Public health is limited to minimal liveness/readiness; detailed health is
  protected.
- Every unsafe route is classified in a generated manifest and enforced by tests
  and production startup checks.
- State-changing routes require authenticated identity and appropriate roles.
- High-risk mutations emit durable redacted audit events.
- Mandatory-audit mutations roll back if the audit event cannot be written.
- Audit read/export/retention permissions are implemented and documented.
- Tests cover config hardening, identity parsing, permissions, redaction, and
  representative audited mutations.
- Docs include deployment requirements and explicitly warn that trusted headers
  require strip-then-set proxy behavior and network isolation from direct FastAPI
  access.
