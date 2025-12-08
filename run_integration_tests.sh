#!/bin/bash
# Integration test runner - automatically runs tests in Docker environment

set -e

echo "🧪 CTIScraper Integration Tests Runner"
echo "========================================"

# Check if Docker is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found"
    exit 1
fi

# Check if containers are running
if ! docker-compose ps | grep -q cti_web; then
    echo "⚠️  Docker containers not running. Starting them..."
    docker-compose up -d
    echo "⏳ Waiting for services to be ready..."
    sleep 10
fi

# Function to run tests in Docker
run_in_docker() {
    local test_file="$1"
    local extra_args="${@:2}"
    
    echo ""
    echo "📦 Running tests in Docker: $test_file"
    echo "-------------------------------------------"
    
    docker-compose exec -T web python -m pytest \
        "$test_file" \
        -v \
        --tb=short \
        --alluredir=/app/allure-results \
        --junit-xml=/app/test-results/junit.xml \
        $extra_args
}

# Run all integration tests
if [ "$1" == "all" ] || [ -z "$1" ]; then
    echo "🚀 Running all integration workflow tests"
    run_in_docker "tests/integration" -m integration_workflow
elif [ "$1" == "celery" ]; then
    run_in_docker "tests/integration/test_celery_workflow_integration.py"
elif [ "$1" == "scoring" ]; then
    run_in_docker "tests/integration/test_scoring_system_integration.py"
elif [ "$1" == "annotation" ]; then
    run_in_docker "tests/integration/test_annotation_feedback_integration.py"
elif [ "$1" == "pipeline" ]; then
    run_in_docker "tests/integration/test_content_pipeline_integration.py"
elif [ "$1" == "source" ]; then
    run_in_docker "tests/integration/test_source_management_integration.py"
elif [ "$1" == "rag" ]; then
    run_in_docker "tests/integration/test_rag_conversation_integration.py"
elif [ "$1" == "error" ]; then
    run_in_docker "tests/integration/test_error_recovery_integration.py"
elif [ "$1" == "backup" ]; then
    run_in_docker "tests/integration/test_export_backup_integration.py"
else
    # Specific test file provided
    run_in_docker "$1" "${@:2}"
fi

echo ""
echo "✅ Integration tests completed"

