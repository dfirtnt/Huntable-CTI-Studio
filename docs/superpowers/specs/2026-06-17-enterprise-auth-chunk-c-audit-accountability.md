# Chunk C — Audit & Accountability: Table, Service, Atomic Mutations, Retention (Build Spec)

- **Date:** 2026-06-17
- **Status:** Draft chunk spec (plan-sized)
- **Parent:** [`2026-06-17-enterprise-auth-auditability-build-spec.md`](2026-06-17-enterprise-auth-auditability-build-spec.md)
- **Parent slices covered:** Slice 4 (audit table & service) + Slice 5 (audit high-risk mutations) + the Audit Access/Retention/Tamper operational controls + Service/Worker identity wiring
- **Build order:** **3 of 3** — depends on Chunk A (actor identity, service-identity types) and Chunk B (the guard that produces denials and the roles that gate audit read/export).

---

## Why this is independently shippable

Chunks A and B make the app *secure*. Chunk C makes it *accountable*: durable, redacted audit events for every security-relevant and data-changing action, written atomically with the mutation so the record can't silently diverge from reality. This is the deepest and riskiest chunk — it requires refactoring service transaction boundaries — which is precisely why it is isolated from the route-breadth work in Chunk B.

---

## Scope

### In scope
- **`AuditEventTable`** in [`src/database/models.py`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/database/models.py) with the parent spec's field set (`id`, `created_at`, `request_id`, `actor_type`, `actor_id`, `actor_email`, `actor_roles`, `source_ip`, `user_agent`, `action`, `target_type`, `target_id`, `status`, `summary`, `metadata` JSONB, `before_hash`, `after_hash`, `error_code`) and indexes on `created_at`, `actor_id`, `action`, (`target_type`,`target_id`), `request_id`.
- **Schema creation via the existing `create_tables()` idempotent path** (`src/database/async_manager.py:137–186`) — **not Alembic** (none exists). Table + indexes are part of the required schema-creation path; add `ALTER TABLE ... ADD ... IF NOT EXISTS`-style idempotent ensures consistent with the current pattern.
- **Required-schema startup validation:** production startup fails if the `audit_events` table or any required index is missing. Best-effort DDL skips are not acceptable for mandatory-audit infrastructure.
- **`AuditService` / `AsyncAuditService`** in `src/services/audit_service.py`:
  - Action constants (the parent's `auth.*`, `settings.*`, `source.*`, `scheduled_jobs.*`, `workflow.*`, `sigma_queue.*`, `annotation.*`, `export.*`, `debug.*`).
  - Redaction helpers: never persist API keys, GitHub/provider tokens, passwords, connection strings, session cookies, Authorization headers, or raw provider payloads. Secrets recorded as presence/change booleans + SHA-256 hashes of redacted snapshots only.
  - `record_mandatory(session, event)` (sync) and async equivalent that **require a caller-owned session** and commit the mutation and audit event in one transaction.
- **Mandatory-audit transaction refactors:** for each high-risk action (settings, secret, source config, scheduled job, sigma approve/reject/bulk/PR, workflow cancel/cleanup, debug), ensure the route shares one transaction boundary with the audit write. Where a service currently opens-and-commits internally, refactor it to accept an existing session before marking that route enterprise-ready. If transaction sharing is impossible for a route, classify it not-enterprise-ready and keep it denied in auth-enabled production until refactored. **No "commit mutation, then try to audit"** for these actions.
- **Audit the high-risk mutations** identified in Chunk B's route-protection table: one success + one denied test per route family. Secret changes audit presence/change only; bulk actions summarize counts + target IDs, not full payloads.
- **Wire `auth.request_denied`** from Chunk B's denial path now that the audit service exists.
- **Service/worker identity wiring:** attach the Chunk A service-identity types (`service:celery-worker`, `service:workflow-worker`, `service:scheduler`, `service:cli`) to audit events created in worker/scheduler/CLI code; copy the initiating human identity into workflow/task metadata where available. Internal HTTP service calls use an explicit service identity header, never reused human trusted headers.
- **Audit access / retention / tamper controls:**
  - Audit read requires `admin` by default; `operator` sees audit *readiness* (via detailed health) but not contents.
  - Audit export requires `admin` and emits `audit.exported`.
  - `AUDIT_RETENTION_DAYS` (default `365`); retention deletion requires `admin`, never automatic in local dev, emits `audit.retention_applied`.
  - Docs state plainly that phase-one audit storage is DB-backed and mutable by DBAs; recommend shipping audit exports / DB logs to an external SIEM for higher assurance. Do not oversell the log as immutable.

### Explicitly deferred (parent non-goals)
- Signed/externally-immutable audit ledger.
- Per-user data ownership migration.

---

## Codebase ground truth (verified 2026-06-17)
- **No existing audit table or audit service** — clean slate (`models.py` has only comments mentioning "audit").
- Schema is **`create_all` + idempotent `ALTER TABLE` with lock timeouts** (`src/database/async_manager.py:137–186`); there is **no Alembic**. The audit DDL must follow this pattern, and the "required schema, not best-effort" rule applies on top of it.
- Some services currently open and commit their own sessions — these are the transaction-refactor targets and the primary risk in this chunk.

---

## Files
- Modify: `src/database/models.py` (`AuditEventTable`), `src/database/async_manager.py` (`create_tables` ensures + startup validation)
- Create: `src/services/audit_service.py`
- Modify: settings/sources/workflow/scheduled-jobs/sigma-queue/annotations/export/debug routes (+ the services they call, for shared transactions); worker/scheduler/CLI entrypoints for service identity
- Test: redaction, audit writes, atomic rollback, per-route-family success/denied, schema-validation startup, export/retention permissions

## Acceptance
- Audit table + indexes created on new installs; production startup fails if they're missing.
- Redaction strips secrets from nested metadata; secret updates record presence/change only.
- A mandatory-audit write failure rolls back the associated mutation (atomic).
- Each listed high-risk action emits exactly one `success`/`failure`/`denied` event carrying actor, request ID, action, target, status, and redacted metadata.
- Workflow retry/cancel carries the initiating actor into execution/task metadata where applicable.
- Audit read/export/retention require `admin` and emit their own events.

## Testing
`python3 run_tests.py` for affected unit/integration/API suites; targeted tests per route family.
