#!/bin/bash
# Unified test runner script for CTI Scraper
# This script provides a simple interface to the Python test runner

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "CTI Scraper Unified Test Runner"
    echo ""
    echo "Usage: $0 [OPTIONS] [TEST_TYPE]"
    echo ""
    echo "Test Types:"
    echo "  smoke        Quick health check (~30s)"
    echo "  unit         Unit tests only (~1m)"
    echo "  api          API endpoint tests (~2m)"
    echo "  integration  System integration tests (~3m)"
    echo "  ui           Web interface tests (~5m)"
    echo "  all          Complete test suite (~8m)"
    echo ""
    echo "Options:"
    echo "  --docker     Run tests in Docker containers"
    echo "  --coverage   Generate coverage report"
    echo "  --install    Install test dependencies"
    echo "  --help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 smoke                    # Quick health check"
    echo "  $0 all --coverage           # Full suite with coverage"
    echo "  $0 integration --docker     # Docker-based integration tests"
    echo "  $0 --install                # Install test dependencies"
}

# Default values
TEST_TYPE="smoke"
DOCKER_MODE=false
COVERAGE=false
INSTALL=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            DOCKER_MODE=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --install)
            INSTALL=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        smoke|unit|api|integration|ui|all)
            TEST_TYPE="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "run_tests.py" ]]; then
    print_error "run_tests.py not found. Please run this script from the project root."
    exit 1
fi

# Build the command
CMD="python run_tests.py"

# Add test type
case "$TEST_TYPE" in
    "smoke")
        CMD="$CMD --smoke"
        ;;
    "unit")
        CMD="$CMD --unit"
        ;;
    "api")
        CMD="$CMD --api"
        ;;
    "integration")
        CMD="$CMD --integration"
        ;;
    "ui")
        CMD="$CMD --ui"
        ;;
    "all")
        CMD="$CMD --all"
        ;;
esac

# Add options
if [[ "$DOCKER_MODE" == true ]]; then
    CMD="$CMD --docker"
fi

if [[ "$COVERAGE" == true ]]; then
    CMD="$CMD --coverage"
fi

if [[ "$INSTALL" == true ]]; then
    CMD="$CMD --install"
fi

# Run the tests
print_status "Running $TEST_TYPE tests..."
print_status "Command: $CMD"

if eval $CMD; then
    print_success "Tests completed successfully!"
    
    if [[ "$COVERAGE" == true ]]; then
        print_status "Coverage report generated in htmlcov/"
    fi
else
    print_error "Tests failed!"
    exit 1
fi
