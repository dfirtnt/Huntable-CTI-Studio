"""Route authorization manifest and coverage validation.

Chunk B uses this as the route-surface source of truth. It intentionally
validates the registered FastAPI app instead of parsing route source files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi.routing import APIRoute
from starlette.routing import Mount

from src.web.security.config import AuthMode, SecurityConfig

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class RouteClassification(StrEnum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ROLES = "roles"


class AuditRequirement(StrEnum):
    NONE = "none"
    BEST_EFFORT = "best_effort"
    MANDATORY = "mandatory"


class CsrfRequirement(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    SERVICE_ONLY = "service_only"


@dataclass(frozen=True)
class RouteManifestEntry:
    method: str
    path: str
    endpoint_name: str
    route_module: str
    classification: RouteClassification
    roles: tuple[str, ...] = ()
    audit_requirement: AuditRequirement = AuditRequirement.NONE
    csrf_requirement: CsrfRequirement = CsrfRequirement.NOT_REQUIRED

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def is_unsafe(self) -> bool:
        return self.method in UNSAFE_METHODS


@dataclass(frozen=True)
class RouteRule:
    pattern: str
    classification: RouteClassification
    roles: tuple[str, ...] = ()
    audit_requirement: AuditRequirement = AuditRequirement.NONE
    csrf_requirement: CsrfRequirement = CsrfRequirement.NOT_REQUIRED
    methods: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()

    def matches(self, entry: RouteManifestEntry) -> bool:
        if self.methods and entry.method not in self.methods:
            return False
        if self.modules and entry.route_module not in self.modules:
            return False
        if self.pattern.endswith("*"):
            return entry.path.startswith(self.pattern[:-1])
        return entry.path == self.pattern


PUBLIC_PATHS = frozenset({"/health", "/api/health", "/static/{path:path}"})

_OPERATOR_ADMIN = ("operator", "admin")
_RULE_REVIEWER_ADMIN = ("rule_reviewer", "admin")
_ANALYST_ADMIN = ("analyst", "admin")
_ANALYST_OPERATOR_ADMIN = ("analyst", "operator", "admin")
_ADMIN = ("admin",)


UNSAFE_ROUTE_RULES: tuple[RouteRule, ...] = (
    # Admin-only controls and dangerous maintenance.
    RouteRule("/api/backup/*", RouteClassification.ROLES, _ADMIN, AuditRequirement.MANDATORY, CsrfRequirement.REQUIRED),
    RouteRule("/api/audit/*", RouteClassification.ROLES, _ADMIN, AuditRequirement.MANDATORY, CsrfRequirement.REQUIRED),
    RouteRule(
        "/api/settings*", RouteClassification.ROLES, _ADMIN, AuditRequirement.MANDATORY, CsrfRequirement.REQUIRED
    ),
    RouteRule(
        "/api/model/*",
        RouteClassification.ROLES,
        _ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/observables/training/*",
        RouteClassification.ROLES,
        _ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    # Operator surfaces.
    RouteRule(
        "/api/cron", RouteClassification.ROLES, _OPERATOR_ADMIN, AuditRequirement.MANDATORY, CsrfRequirement.REQUIRED
    ),
    RouteRule(
        "/api/scheduled-jobs",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/sources/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/workflow/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/embeddings/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/articles/{article_id}/embed",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/evaluations/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/eval/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/observables/evaluation/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/ml-model-performance/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/actions/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/test-*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/validate-model",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/load-lmstudio-model",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/articles/*",
        RouteClassification.ROLES,
        _OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
        modules=("ai", "llm_optimized_endpoint"),
    ),
    # Rule review surfaces.
    RouteRule(
        "/api/sigma-queue/*",
        RouteClassification.ROLES,
        _RULE_REVIEWER_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/sigma-ab-test/*",
        RouteClassification.ROLES,
        _RULE_REVIEWER_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/sigma-similarity-test/*",
        RouteClassification.ROLES,
        _RULE_REVIEWER_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    # Analyst data mutation and ingest surfaces.
    RouteRule(
        "/api/articles/{article_id}/annotations*",
        RouteClassification.ROLES,
        _ANALYST_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/annotations/*",
        RouteClassification.ROLES,
        _ANALYST_ADMIN,
        AuditRequirement.MANDATORY,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/scrape-url",
        RouteClassification.ROLES,
        _ANALYST_OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/vision/extract",
        RouteClassification.ROLES,
        _ANALYST_OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/pdf/*",
        RouteClassification.ROLES,
        _ANALYST_OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
    ),
    # Destructive article-data mutations (delete, bulk delete/update, mark-reviewed)
    # live in the `articles` module and must require a role, not just authentication.
    # This rule precedes the authenticated catch-all so zero-role users cannot delete
    # articles. (The `ai`/`llm_optimized_endpoint` article actions are role-gated above.)
    RouteRule(
        "/api/articles/*",
        RouteClassification.ROLES,
        _ANALYST_OPERATOR_ADMIN,
        AuditRequirement.BEST_EFFORT,
        CsrfRequirement.REQUIRED,
        modules=("articles",),
    ),
    # Article-local actions and semantic search stay authenticated in this pass.
    RouteRule(
        "/api/articles/*",
        RouteClassification.AUTHENTICATED,
        audit_requirement=AuditRequirement.BEST_EFFORT,
        csrf_requirement=CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/search/semantic",
        RouteClassification.AUTHENTICATED,
        audit_requirement=AuditRequirement.BEST_EFFORT,
        csrf_requirement=CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/analytics/events",
        RouteClassification.AUTHENTICATED,
        audit_requirement=AuditRequirement.BEST_EFFORT,
        csrf_requirement=CsrfRequirement.REQUIRED,
    ),
    RouteRule(
        "/api/feedback/*",
        RouteClassification.AUTHENTICATED,
        audit_requirement=AuditRequirement.BEST_EFFORT,
        csrf_requirement=CsrfRequirement.REQUIRED,
    ),
)


SAFE_ROUTE_RULES: tuple[RouteRule, ...] = (
    RouteRule("/health", RouteClassification.PUBLIC),
    RouteRule("/api/health", RouteClassification.PUBLIC),
    RouteRule("/static/{path:path}", RouteClassification.PUBLIC),
    RouteRule("/api/health/*", RouteClassification.ROLES, _OPERATOR_ADMIN),
    RouteRule("/api/capabilities", RouteClassification.ROLES, _OPERATOR_ADMIN),
    RouteRule("/api/audit/*", RouteClassification.ROLES, _ADMIN),
    RouteRule("/api/debug/*", RouteClassification.ROLES, _ADMIN),
)


def route_entries(app: Any) -> list[RouteManifestEntry]:
    entries: list[RouteManifestEntry] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            module = route.endpoint.__module__.rsplit(".", 1)[-1]
            for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
                entries.append(
                    RouteManifestEntry(
                        method=method,
                        path=route.path,
                        endpoint_name=route.endpoint.__name__,
                        route_module=module,
                        classification=RouteClassification.AUTHENTICATED,
                    )
                )
        elif isinstance(route, Mount) and route.path == "/static":
            entries.append(
                RouteManifestEntry(
                    method="GET",
                    path="/static/{path:path}",
                    endpoint_name="static",
                    route_module="static",
                    classification=RouteClassification.PUBLIC,
                )
            )
    return entries


def classify_entry(entry: RouteManifestEntry) -> RouteManifestEntry:
    rules = UNSAFE_ROUTE_RULES if entry.is_unsafe else SAFE_ROUTE_RULES
    for rule in rules:
        if rule.matches(entry):
            return RouteManifestEntry(
                method=entry.method,
                path=entry.path,
                endpoint_name=entry.endpoint_name,
                route_module=entry.route_module,
                classification=rule.classification,
                roles=rule.roles,
                audit_requirement=rule.audit_requirement,
                csrf_requirement=rule.csrf_requirement,
            )
    if entry.is_unsafe:
        return entry
    return RouteManifestEntry(
        method=entry.method,
        path=entry.path,
        endpoint_name=entry.endpoint_name,
        route_module=entry.route_module,
        classification=RouteClassification.AUTHENTICATED,
    )


def build_route_manifest(app: Any) -> list[RouteManifestEntry]:
    return [classify_entry(entry) for entry in route_entries(app)]


_PATH_PARAM_RE = re.compile(r"\{[^}/]+(?::[^}/]+)?\}")


def _path_template_matches(template: str, path: str) -> bool:
    if template == path:
        return True
    parts: list[str] = []
    pos = 0
    for match in _PATH_PARAM_RE.finditer(template):
        parts.append(re.escape(template[pos : match.start()]))
        parts.append(r"[^/]+")
        pos = match.end()
    parts.append(re.escape(template[pos:]))
    pattern = "^" + "".join(parts) + "$"
    return re.match(pattern, path) is not None


def find_manifest_entry(
    manifest: list[RouteManifestEntry],
    method: str,
    path: str,
) -> RouteManifestEntry | None:
    normalized_method = method.upper()
    for entry in manifest:
        if entry.method == normalized_method and _path_template_matches(entry.path, path):
            return entry
    return None


# Unsafe routes that are *intentionally* authenticated-only (no role gate). Every
# entry here is a deliberate, reviewed decision. Any unsafe route that resolves to
# AUTHENTICATED but is not on this list -- whether it fell through to the default
# fallback or was downgraded by a catch-all rule -- is surfaced by
# unclassified_unsafe_routes() so it cannot silently ship under-protected.
AUTHENTICATED_UNSAFE_ALLOWLIST = frozenset(
    {
        "POST /api/analytics/events",
        "POST /api/feedback/chunk-classification",
        "POST /api/search/semantic",
    }
)


def unclassified_unsafe_routes(app: Any) -> list[RouteManifestEntry]:
    """Unsafe routes that lack a role gate and are not explicitly allowlisted.

    Flags any unsafe (POST/PUT/PATCH/DELETE) route whose classification is merely
    AUTHENTICATED unless it is on AUTHENTICATED_UNSAFE_ALLOWLIST. This catches both
    truly-unclassified routes (default fallback) and routes silently downgraded to
    AUTHENTICATED by a broad rule -- the latter is invisible to a metadata-only check.
    """
    manifest = build_route_manifest(app)
    return [
        entry
        for entry in manifest
        if entry.is_unsafe
        and entry.classification is RouteClassification.AUTHENTICATED
        and entry.key not in AUTHENTICATED_UNSAFE_ALLOWLIST
    ]


def validate_route_manifest(app: Any, config: SecurityConfig) -> None:
    missing = unclassified_unsafe_routes(app)
    if not missing:
        return
    fail_closed = config.is_production or config.auth_mode is not AuthMode.DISABLED
    if not fail_closed:
        return
    details = ", ".join(f"{entry.key} ({entry.route_module}.{entry.endpoint_name})" for entry in missing)
    raise RuntimeError(f"Unsafe routes without a role gate and not in AUTHENTICATED_UNSAFE_ALLOWLIST: {details}")
