# Chunk B — Route Authorization: Manifest, Deny-by-Default, Roles & CSRF (Build Spec)

- **Date:** 2026-06-17
- **Status:** Draft chunk spec (plan-sized)
- **Parent:** [`2026-06-17-enterprise-auth-auditability-build-spec.md`](2026-06-17-enterprise-auth-auditability-build-spec.md)
- **Parent slices covered:** Slice 3 (route manifest, global auth guard, permission helpers) + Slice 6 (CSRF) + the `SECRET_KEY` fail-closed check deferred from Chunk A
- **Build order:** **2 of 3** — depends on Chunk A (consumes `RequestIdentity`, `AUTH_MODE`, roles, the `permissions.py` stub).

---

## Why this is independently shippable

Chunk A established *who the caller is*. Chunk B enforces *what they may do*: a deny-by-default authorization layer over all 259 routes, role gates on the high-risk surface, and CSRF for cookie-backed browser auth. After Chunk B the app is a properly guarded multi-role application — even before durable audit (Chunk C) exists. The audit layer is additive accountability on top of an already-enforced boundary.

This is the **largest-surface, highest-grind** chunk (259 endpoints across 36 modules) and is deliberately isolated so its breadth doesn't entangle the audit transaction refactors.

---

## Scope

### In scope
- **Route manifest** (`src/web/security/route_manifest.py`): enumerate every route registered by `register_routes()` in [`src/web/routes/__init__.py`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/web/routes/__init__.py) with: path, methods, route module, endpoint name, public/authenticated/role classification, audit requirement (`none` | `best_effort` | `mandatory`), CSRF requirement for unsafe browser routes.
- **Enforcement of the manifest** in two places:
  - A test fails if any unsafe-method route (`POST`/`PUT`/`PATCH`/`DELETE`) lacks a classification.
  - Production startup fails if any unsafe-method route is unclassified. Auth-enabled development uses the same fail-closed behavior; only `AUTH_MODE=disabled` development may log-and-continue.
- **Permission helpers** (flesh out the Chunk A stub in `src/web/security/permissions.py`): `require_authenticated`, `require_role("admin")`, `require_any_role("operator","admin")`, and `require_permission(...)` only if role checks prove too coarse (YAGNI by default).
- **Global auth guard** (middleware): when auth is enabled, all non-public routes require an authenticated identity; unsafe methods additionally require an explicit permission dependency or an allowlisted classification, else 403.
- **Public allowlist:** `/health`, `/api/health`, `/static/*`, one optional readiness path. Nothing else public. `/docs` and `/openapi.json` not public in production unless explicitly configured.
- **Role dependencies** applied to the parent spec's "Route Protection Targets" table — Settings/credentials (`admin`), source add/update/toggle/collect (`operator`/`admin`), scheduled jobs (`operator`/`admin`), workflow trigger/retry/cancel/cleanup (`operator`/`admin`), sigma queue edit/approve/reject/bulk/enrich/validate/PR (`rule_reviewer`/`admin`), annotations (`analyst`/`admin`), backup (`admin`), model retrain/rollback/version (`admin`), embeddings rebuild (`operator`/`admin`), scrape/PDF upload (`analyst`/`operator`/`admin`), eval runs/backfills/diagnostics (`operator`/`admin`), observable training (`admin`), AI action endpoints (default `operator`/`admin`), semantic search (authenticated), export (authenticated; revisit per open question), debug (`admin`).
- **Detailed health → `operator`/`admin`.** Only minimal liveness/readiness stays public; the rich endpoints in [`src/web/routes/health.py`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/web/routes/health.py) (DB counts, dedup/SimHash internals, Redis/Celery state, model names, OCR/LangFuse status, ingestion analytics) move behind a role.
- **`SECRET_KEY` fail-closed check** (moved here from Chunk A): production fails to start if `SECRET_KEY` is missing/default — now meaningful because CSRF below uses it.
- **CSRF decision + implementation:** if the proxy authenticates the browser with cookies, issue a signed per-session CSRF token, render it into base templates, require `X-CSRF-Token` on unsafe browser requests, update frontend fetch helpers. If deployed auth is bearer-only and cookieless, document explicitly why CSRF is inactive — never leave it implicit.

### Explicitly deferred
- Durable audit events for denials and mutations (Chunk C). In this chunk, denials return 403 and may log; the `auth.request_denied` audit event is wired in Chunk C.
- Mandatory-audit transaction refactors (Chunk C).

---

## Codebase ground truth (verified 2026-06-17)
- **36 route modules, 259 route decorators**, centrally registered in `src/web/routes/__init__.py:52–97` via `register_routes(app)`. The manifest generator should walk the registered `app.routes` after registration, not re-parse files.
- Health endpoints confirmed leaky across 8 routes in `routes/health.py` — they are the primary justification for gating detailed health.
- **Resolved (2026-06-18):** the parent spec's "Existing tests intentionally prevent explicit auth dependencies on some source endpoints" claim **is accurate** — the load-bearing test is [`tests/api/test_backup_cron_api.py::test_backup_endpoints_require_no_admin_auth`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/tests/api/test_backup_cron_api.py), which asserts backup/cron endpoints accept requests with **no** auth header (the Settings UI sends none). Sibling no-auth assertions also live in `tests/api/test_sources_routes.py`, `tests/api/test_cron_api.py`, and `tests/test_web_application.py`. The pre-Chunk-A `docs/guides/authentication.md` explicitly warned: *"Do not re-introduce the in-app X-API-Key check — `test_backup_endpoints_require_no_admin_auth` will fail and the Settings UI will silently break."*
  - **Chunk B consequence:** deny-by-default route protection on backup/cron/source endpoints **will** break these tests. That is expected and intended — Chunk B's migration task must update them to assert the *new* auth model (authenticated identity required when `AUTH_MODE` is enabled; local-dev `disabled` mode still passes with the synthetic admin identity), rather than dropping the migration. Do not silently delete the assertions; rewrite them to encode the new contract.

---

## Files
- Create: `src/web/security/route_manifest.py`; expand `src/web/security/permissions.py`
- Modify: middleware wiring in `src/web/modern_main.py`; role dependencies across `src/web/routes/*.py` (high-risk groups); `routes/health.py` (gate detailed health); base templates + frontend fetch helpers for CSRF
- Test: `tests/api/` for representative route groups + the manifest-completeness test

## Acceptance
- Public health works unauthenticated; detailed health requires `operator`/`admin`.
- Static assets still load unauthenticated where proxy/login UX needs them.
- Any unsafe, unclassified route fails the manifest test **and** fails production startup.
- Settings mutation requires `admin`; Sigma approval requires `rule_reviewer`/`admin`; workflow retry/cancel requires `operator`/`admin`.
- Backup/restore, model retrain/rollback, embeddings update, scrape/PDF upload, eval runs/backfills/diagnostics, observable training, AI actions, and semantic search all have explicit classifications.
- Unsafe browser requests without a CSRF token fail when CSRF is enabled; existing UI flows include the token automatically; non-browser service routes don't accidentally bypass via CSRF exemption.

## Testing
`python3 run_tests.py api` (or focused API tests via `run_tests.py --paths`); `python3 run_tests.py ui` or focused Playwright for CSRF/fetch changes.
