#!/bin/bash

# Shared startup helpers for setup.sh and start.sh.

startup_url_link() { printf '\e]8;;%s\e\\%s\e]8;;\e\\' "$1" "${2:-$1}"; }

_startup_log_info() {
    if declare -F print_status >/dev/null 2>&1; then
        print_status "$1"
    else
        echo "$1"
    fi
}

_startup_log_warn() {
    if declare -F print_warning >/dev/null 2>&1; then
        print_warning "$1"
    else
        echo "⚠️  $1"
    fi
}

_startup_log_error() {
    if declare -F print_error >/dev/null 2>&1; then
        print_error "$1"
    else
        echo "❌ $1"
    fi
}

startup_check_directory() {
    if [ ! -f "docker-compose.yml" ]; then
        _startup_log_error "Please run this script from the CTI Scraper root directory."
        return 1
    fi
}

startup_check_prerequisites() {
    DOCKER_CMD=""
    if command -v docker >/dev/null 2>&1; then
        DOCKER_CMD="docker"
    elif [ -f "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
        DOCKER_CMD="/Applications/Docker.app/Contents/Resources/bin/docker"
        export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
        _startup_log_info "Found Docker at /Applications/Docker.app/Contents/Resources/bin/docker"
    else
        _startup_log_error "Docker executable not found in PATH."
        _startup_log_error "Please install/start Docker Desktop and ensure docker is in PATH."
        return 1
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker-compose"
    elif $DOCKER_CMD compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="$DOCKER_CMD compose"
    else
        _startup_log_error "Docker Compose is not available."
        return 1
    fi

    if ! $DOCKER_CMD info >/dev/null 2>&1; then
        _startup_log_error "Docker is not running. Please start Docker Desktop first."
        return 1
    fi
}

startup_ensure_runtime_directories() {
    _startup_log_info "Creating necessary directories..."
    mkdir -p logs backups models outputs data
}

startup_set_env_key() {
    local env_file="$1"
    local key="$2"
    local value="$3"

    if [ ! -f "$env_file" ]; then
        return 1
    fi

    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^${key}=.*|${key}=${value}|" "$env_file"
        else
            sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
        fi
    else
        echo "${key}=${value}" >>"$env_file"
    fi
}

startup_disable_lmstudio() {
    local env_file="${1:-.env}"
    startup_set_env_key "$env_file" "WORKFLOW_LMSTUDIO_ENABLED" "false"
    startup_set_env_key "$env_file" "PROCEED_WITHOUT_LMSTUDIO" "1"
    startup_set_env_key "$env_file" "LMSTUDIO_API_URL" ""
    startup_set_env_key "$env_file" "LMSTUDIO_EMBEDDING_URL" ""
}

startup_apply_platform_compatibility() {
    local env_file="${1:-.env}"
    local non_interactive="${2:-false}"
    SKIP_SIGMA_INDEX=""
}

startup_start_services() {
    _startup_log_info "Stopping existing containers..."
    $DOCKER_COMPOSE_CMD down --remove-orphans

    _startup_log_info "Building and starting stack..."
    $DOCKER_COMPOSE_CMD up --build -d

    _startup_log_info "Waiting for services to be ready..."
    sleep 15
}

startup_verify_core_services() {
    local ok=true

    _startup_log_info "Checking service health..."
    if $DOCKER_COMPOSE_CMD exec -T postgres pg_isready -U cti_user -d cti_scraper >/dev/null 2>&1; then
        _startup_log_info "✅ PostgreSQL is healthy"
    else
        _startup_log_error "PostgreSQL is not ready"
        $DOCKER_COMPOSE_CMD logs postgres || true
        ok=false
    fi

    if $DOCKER_COMPOSE_CMD exec -T redis redis-cli ping >/dev/null 2>&1; then
        _startup_log_info "✅ Redis is healthy"
    else
        _startup_log_error "Redis is not ready"
        $DOCKER_COMPOSE_CMD logs redis || true
        ok=false
    fi

    if curl -fsS http://localhost:8001/health >/dev/null 2>&1; then
        _startup_log_info "✅ Web service is healthy"
    else
        _startup_log_error "Web service is not ready"
        $DOCKER_COMPOSE_CMD logs web || true
        ok=false
    fi

    [ "$ok" = true ]
}

startup_migrate_pgvector_indexes() {
    echo ""
    _startup_log_info "Checking pgvector indexes..."
    if $DOCKER_COMPOSE_CMD run --rm cli python scripts/migrate_pgvector_indexes.py 2>/dev/null; then
        _startup_log_info "✅ pgvector indexes OK"
    else
        _startup_log_warn "pgvector migration failed (embedding writes may fail)"
    fi
}

startup_sigma_sync_and_index() {
    echo ""
    _startup_log_info "Sigma: syncing SigmaHQ repo..."
    if $DOCKER_COMPOSE_CMD run --rm cli python -m src.cli.main sigma sync 2>/dev/null; then
        if $DOCKER_COMPOSE_CMD run --rm cli python -m src.cli.main sigma index-metadata 2>/dev/null; then
            _startup_log_info "✅ Sigma rule metadata indexed"
        else
            _startup_log_warn "Sigma metadata index failed (run manually: ./run_cli.sh sigma index-metadata)"
        fi

        if [ -z "$SKIP_SIGMA_INDEX" ]; then
            if $DOCKER_COMPOSE_CMD run --rm cli python -m src.cli.main sigma index-embeddings 2>/dev/null; then
                _startup_log_info "✅ Sigma rule embeddings generated"
            else
                _startup_log_warn "Sigma embeddings skipped (run manually: \"./run_cli.sh sigma index-embeddings\")"
            fi
        else
            # When user chose "No RAG" in setup, RAG_DISABLED_BY_USER is set; skip the warning (they already got instructions).
            if [ -z "${RAG_DISABLED_BY_USER:-}" ]; then
                _startup_log_warn "Skipping Sigma embeddings (limited-env mode). Run \"./run_cli.sh sigma index-embeddings\" when ready."
            fi
        fi
    else
        _startup_log_warn "Sigma sync failed (run manually: ./run_cli.sh sigma sync)"
    fi
}

startup_show_capability_warnings() {
    echo ""
    _startup_log_info "Checking feature capabilities..."
    CAP_JSON=$($DOCKER_COMPOSE_CMD run --rm cli python -m src.cli.main capabilities check --json-output 2>/dev/null || echo '{}')

    if command -v python3 >/dev/null 2>&1 && [ "$CAP_JSON" != "{}" ]; then
        _cap_val() {
            python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get(sys.argv[2],{}).get(sys.argv[3],''))" "$CAP_JSON" "$1" "$2" 2>/dev/null
        }

        sigma_ret=$(_cap_val sigma_retrieval enabled)
        sigma_nov=$(_cap_val sigma_novelty_comparison enabled)
        llm_gen=$(_cap_val llm_generation enabled)

        if [ "$sigma_ret" = "False" ]; then
            echo "  ⚠️  Sigma rule search in RAG: unavailable ($(_cap_val sigma_retrieval reason))"
            echo "     → $(_cap_val sigma_retrieval action)"
        else
            echo "  ✅ Sigma rule search in RAG: available"
        fi

        if [ "$sigma_nov" = "False" ]; then
            echo "  ⚠️  Sigma novelty comparison: unavailable ($(_cap_val sigma_novelty_comparison reason))"
        else
            echo "  ✅ Sigma novelty comparison: available"
        fi

        if [ "$llm_gen" = "False" ]; then
            echo "  ⚠️  LLM answer generation: unavailable ($(_cap_val llm_generation reason))"
            echo "     → $(_cap_val llm_generation action)"
        else
            echo "  ✅ LLM answer generation: available ($(_cap_val llm_generation reason))"
        fi
    fi
}

startup_seed_eval_articles() {
    echo ""
    _startup_log_info "Eval articles: seeding from config/eval_articles_data..."
    if $DOCKER_COMPOSE_CMD run --rm cli python scripts/seed_eval_articles_to_db.py 2>/dev/null; then
        _startup_log_info "✅ Eval articles seeded (or already present)"
    else
        _startup_log_warn "Eval articles seed failed (run manually: $DOCKER_COMPOSE_CMD run --rm cli python scripts/seed_eval_articles_to_db.py)"
    fi
}

startup_refresh_provider_model_catalog() {
    echo ""
    _startup_log_info "Refreshing LLM provider model catalog..."
    if $DOCKER_COMPOSE_CMD run --rm cli python3 scripts/maintenance/update_provider_model_catalogs.py --write 2>/dev/null; then
        _startup_log_info "✅ Provider model catalog updated"
    else
        _startup_log_warn "Provider model catalog refresh skipped (set OPENAI_API_KEY/ANTHROPIC_API_KEY in .env for API refresh)"
    fi
}

startup_build_and_serve_mkdocs() {
    if [ ! -f "mkdocs.yml" ]; then
        return 0
    fi

    echo ""
    _startup_log_info "Building docs (MkDocs)..."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    local py=".venv/bin/python3"
    "$py" -m pip install -q mkdocs mkdocs-material
    if ! "$py" -m mkdocs build --strict 2>/dev/null; then
        "$py" -m mkdocs build
    fi

    local start_mkdocs=true
    local existing_pids
    existing_pids="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$existing_pids" ]; then
        local mkdocs_pids=""
        local pid
        for pid in $existing_pids; do
            local cmd
            cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
            if [[ "$cmd" == *"mkdocs serve"* ]]; then
                mkdocs_pids="$mkdocs_pids $pid"
            fi
        done
        if [ -n "${mkdocs_pids// }" ]; then
            _startup_log_info "Restarting existing MkDocs server on :8000..."
            # shellcheck disable=SC2086
            kill $mkdocs_pids
            sleep 1
        else
            _startup_log_warn "Port 8000 is in use by a non-MkDocs process; skipping docs auto-start."
            start_mkdocs=false
        fi
    fi

    if [ "$start_mkdocs" = true ]; then
        _startup_log_info "Starting MkDocs server in background..."
        mkdir -p logs
        nohup "$py" -m mkdocs serve -a 127.0.0.1:8000 >> logs/mkdocs.log 2>&1 </dev/null &
        disown -h
    fi
}

startup_show_running_stack_summary() {
    echo ""
    echo "🎉 CTI Scraper is running!"
    echo ""
    echo "📊 Services:"
    echo -n "   • Web Interface: "; startup_url_link "http://localhost:8001"; echo
    echo -n "   • Docs:         "; startup_url_link "http://localhost:8000"; echo " (MkDocs; logs: logs/mkdocs.log)"
    echo "   • PostgreSQL:    postgres:5432 (Docker container)"
    echo "   • Redis:         redis:6379 (Docker container)"
    echo ""
    echo "🔧 Management:"
    echo "   • CLI Commands:  ./run_cli.sh <command>"
    echo "   • View logs:     $DOCKER_COMPOSE_CMD logs -f [service]"
    echo "   • Stop stack:    $DOCKER_COMPOSE_CMD down"
    echo "   • Restart:       $DOCKER_COMPOSE_CMD restart [service]"
    echo ""
    echo "📈 Monitoring:"
    echo -n "   • Health check:  "; startup_url_link "http://localhost:8001/health"; echo
    echo -n "   • Database stats: "; startup_url_link "http://localhost:8001/api/sources"; echo
    echo ""
    echo "🐳 Running containers:"
    $DOCKER_COMPOSE_CMD ps
    echo ""
    echo "✨ Startup complete!"
    echo ""
}
