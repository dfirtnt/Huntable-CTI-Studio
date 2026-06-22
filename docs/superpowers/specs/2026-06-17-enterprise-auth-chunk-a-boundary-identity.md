# Chunk A — Secure Boundary & Request Identity (Build Spec)

- **Date:** 2026-06-17
- **Status:** Draft chunk spec (plan-sized)
- **Parent:** [`2026-06-17-enterprise-auth-auditability-build-spec.md`](2026-06-17-enterprise-auth-auditability-build-spec.md)
- **Parent slices covered:** Slice 1 (production hardening config) + Slice 2 (identity & request-ID middleware)
- **Build order:** **1 of 3** — no dependencies; A → B → C.

---

## Why this is independently shippable

After Chunk A alone, with **no route guarded yet**:

- The app still runs locally unchanged under `AUTH_MODE=disabled` (synthetic local-dev admin identity).
- The app **refuses to start** in an insecure production posture (auth disabled, wildcard hosts, wildcard CORS).
- The app can sit behind a trusted-header SSO proxy and **populate a verified request identity** that shows up in structured logs and is attached to `request.state.identity`.
- Every response carries `X-Request-ID`.

That is real, testable, valuable software: a secure boundary and an identity context, even before authorization (Chunk B) or audit (Chunk C) exist. Identity is the substrate both later chunks consume.

---

## Scope

### In scope
- New config module `src/web/security/config.py` that parses and validates security env vars at startup.
- `AUTH_MODE` (`disabled` | `trusted_header` | `oidc` no-op) and `APP_ENV`.
- Replace hardcoded wildcards in [`src/web/modern_main.py:184`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/web/modern_main.py#L184) (`allow_origins=["*"]`) and [`:190`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/web/modern_main.py#L190) (`allowed_hosts=["*"]`) with env-driven values; keep current local defaults for development.
- Fail-closed startup checks:
  - `APP_ENV=production` + `AUTH_MODE=disabled` → startup fails unless `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true`.
  - `APP_ENV=production` + wildcard `TRUSTED_HOSTS` → startup fails.
  - `APP_ENV=production` + wildcard `CORS_ALLOWED_ORIGINS` → startup fails.
- Request-ID middleware: accept `X-Request-ID` from trusted proxy if present, else generate UUID, return it on the response, expose on `request.state`.
- `RequestIdentity` type and identity middleware in `src/web/security/identity.py` / `src/web/security/middleware.py`:
  - Trusted-header parsing (`X-Huntable-Verified`, `-User-Id`, `-Email`, `-Name`, `-Groups`, configurable names).
  - Spoof rejection: identity headers without the trusted proxy marker → unauthenticated; identity headers from a peer not in `AUTH_TRUSTED_PROXY_IPS` → rejected.
  - Synthetic local-dev identity for `AUTH_MODE=disabled`: `user_id="local-dev"`, `roles=("admin",)`, `auth_mode="disabled"`.
  - Attach `request.state.identity` and include identity in structured request logs.
- Deterministic group→role mapping driven by env (`AUTH_ADMIN_GROUPS`, `AUTH_ANALYST_GROUPS`, `AUTH_REVIEWER_GROUPS`, `AUTH_OPERATOR_GROUPS`); never hardcode customer group names.
- Service-identity **types** only (`service:celery-worker`, `service:workflow-worker`, `service:scheduler`, `service:cli`) defined in the identity module so Chunk C can attach them to worker audit events. (Wiring them into workers is Chunk C.)
- A `permissions.py` **stub** exposing `require_authenticated` / `require_role` signatures that are inert while no route imports them (the enforcing implementation lands in Chunk B). Stub exists so Chunk B has a stable import target.
- `.env.example` updates with safe commented examples.

### Explicitly deferred
- **`SECRET_KEY` fail-closed check** is deferred to Chunk B — there is no session/cookie/CSRF infrastructure today, so `SECRET_KEY` protects nothing until CSRF lands. (Parent spec lists it under Slice 1; this is a deliberate correction.)
- Any actual route protection (Chunk B).
- Any audit writes (Chunk C). Spoof rejections should be *logged* here; the `auth.request_denied` *audit event* is wired in Chunk C once the audit service exists.

---

## Codebase ground truth (verified 2026-06-17)
- CORS wildcard confirmed at `src/web/modern_main.py:184`; TrustedHost wildcard at `:190`.
- No existing auth/identity middleware; `src/web/dependencies.py` has no auth constructs.
- `APP_ENV` is already read (`src/database/async_manager.py:85`, `routes/health.py:145`, `worker/celery_app.py`) — reuse the same convention.
- `SECRET_KEY`, `TRUSTED_HOSTS`, `CORS_ALLOWED_ORIGINS` are **not** read anywhere today — all net-new env vars.
- There is **no centralized `Settings` class**; env vars are read ad hoc. `src/web/security/config.py` becomes the first centralized security-config surface (do not attempt a global settings refactor here — YAGNI).

---

## Files
- Create: `src/web/security/config.py`, `src/web/security/identity.py`, `src/web/security/middleware.py`, `src/web/security/permissions.py` (stub)
- Modify: `src/web/modern_main.py` (env-driven CORS/TrustedHost, register middleware, startup checks), `.env.example`
- Test: `tests/unit/` and/or `tests/api/` for config validation, identity parsing, spoof rejection, request-ID

## Acceptance
- Production + `AUTH_MODE=disabled` (no break-glass) fails startup; with break-glass true, starts.
- Production + wildcard hosts fails; production + wildcard CORS fails.
- Development still starts with the current local workflow and a synthetic admin identity.
- `trusted_header` mode: missing marker → unauthenticated; forged user headers without marker → ignored; forged headers from an untrusted peer → rejected even with marker.
- Valid trusted headers produce expected roles via deterministic group mapping.
- Every response has `X-Request-ID`; an inbound `X-Request-ID` from the trusted proxy is echoed.

## Testing
`python3 run_tests.py` for the affected suites; targeted unit/API tests plus `python3 run_tests.py smoke`.
