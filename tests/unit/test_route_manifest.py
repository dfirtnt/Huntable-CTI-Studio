from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.web.routes import register_routes
from src.web.security.config import load_security_config
from src.web.security.route_manifest import (
    AuditRequirement,
    CsrfRequirement,
    RouteClassification,
    build_route_manifest,
    unclassified_unsafe_routes,
    validate_route_manifest,
)


def _registered_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
    register_routes(app)
    return app


def _by_key(app: FastAPI) -> dict[str, object]:
    return {entry.key: entry for entry in build_route_manifest(app)}


def test_minimal_health_and_static_are_public():
    entries = _by_key(_registered_app())

    assert entries["GET /health"].classification is RouteClassification.PUBLIC
    assert entries["GET /api/health"].classification is RouteClassification.PUBLIC
    assert entries["GET /static/{path:path}"].classification is RouteClassification.PUBLIC


def test_detailed_health_and_capabilities_are_not_public():
    entries = _by_key(_registered_app())

    detailed_paths = [
        "GET /api/health/database",
        "GET /api/health/services",
        "GET /api/health/celery",
        "GET /api/health/ingestion",
        "GET /api/capabilities",
    ]
    for key in detailed_paths:
        entry = entries[key]
        assert entry.classification is RouteClassification.ROLES
        assert entry.roles == ("operator", "admin")


def test_current_unsafe_routes_are_all_classified():
    missing = unclassified_unsafe_routes(_registered_app())

    assert missing == []


def test_manifest_reports_required_metadata_for_representative_route():
    entries = _by_key(_registered_app())
    entry = entries["POST /api/sigma-queue/{queue_id}/approve"]

    assert entry.path == "/api/sigma-queue/{queue_id}/approve"
    assert entry.method == "POST"
    assert entry.endpoint_name == "approve_queued_rule"
    assert entry.route_module == "sigma_queue"
    assert entry.classification is RouteClassification.ROLES
    assert entry.roles == ("rule_reviewer", "admin")
    assert entry.audit_requirement is AuditRequirement.MANDATORY
    assert entry.csrf_requirement is CsrfRequirement.REQUIRED


def test_module_specific_ai_article_routes_are_operator_gated():
    entries = _by_key(_registered_app())
    entry = entries["POST /api/articles/{article_id}/generate-sigma"]

    assert entry.route_module == "ai"
    assert entry.classification is RouteClassification.ROLES
    assert entry.roles == ("operator", "admin")


def test_synthetic_unclassified_unsafe_route_fails_validation_in_auth_enabled_mode():
    app = FastAPI()

    @app.post("/synthetic-unclassified")
    def synthetic_unclassified():
        return {"ok": True}

    config = load_security_config(
        {
            "APP_ENV": "development",
            "AUTH_MODE": "trusted_header",
            "TRUSTED_HOSTS": "localhost",
            "CORS_ALLOWED_ORIGINS": "http://localhost:8001",
        }
    )

    try:
        validate_route_manifest(app, config)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("validate_route_manifest should fail for unclassified unsafe routes")

    assert "POST /synthetic-unclassified" in message
    assert "synthetic_unclassified" in message


def test_synthetic_unclassified_unsafe_route_logs_through_disabled_development():
    app = FastAPI()

    @app.post("/synthetic-unclassified")
    def synthetic_unclassified():
        return {"ok": True}

    config = load_security_config(
        {
            "APP_ENV": "development",
            "AUTH_MODE": "disabled",
        }
    )

    validate_route_manifest(app, config)
