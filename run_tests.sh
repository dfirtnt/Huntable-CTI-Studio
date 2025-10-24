#!/bin/bash
# CTI Scraper Test Runner (DEPRECATED)
# 
# ⚠️  DEPRECATION NOTICE ⚠️
# This script is deprecated and will be removed in a future version.
# Please use the Python test runner instead:
#   python run_tests.py [options] [test_type]
#
# This script is maintained for backward compatibility only.
# All new development should use the Python interface.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

print_deprecation() {
    echo -e "${CYAN}[DEPRECATED]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "CTI Scraper Test Runner (DEPRECATED)"
    echo ""
    print_deprecation "This script is deprecated. Use 'python run_tests.py' instead."
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
    echo ""
    echo "Recommended Python interface:"
    echo "  python run_tests.py smoke                    # Quick health check"
    echo "  python run_tests.py all --coverage          # Full suite with coverage"
    echo "  python run_tests.py --docker integration    # Docker-based integration tests"
    echo "  python run_tests.py --install               # Install test dependencies"
    echo "  python run_tests.py --help                  # Show all options"
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

# Set up virtual environment
setup_venv() {
    local venv_path=".venv"
    
    # Check if .venv exists
    if [[ ! -d "$venv_path" ]]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$venv_path"
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source "$venv_path/bin/activate"
    
    # Install/upgrade dependencies if needed
    if [[ "$INSTALL" == true ]] || [[ ! -f "$venv_path/pyvenv.cfg" ]]; then
        print_status "Installing test dependencies..."
        pip install -q --upgrade pip
        pip install -q -r requirements.txt
        pip install -q -r requirements-test.txt
    fi
}

# Set up virtual environment
setup_venv

# Build the command - use venv python if available
if [[ -f ".venv/bin/python" ]]; then
    CMD=".venv/bin/python run_tests.py"
else
    CMD="python run_tests.py"
fi

# Add test type (positional argument)
case "$TEST_TYPE" in
    "smoke")
        CMD="$CMD smoke"
        ;;
    "unit")
        CMD="$CMD unit"
        ;;
    "api")
        CMD="$CMD api"
        ;;
    "integration")
        CMD="$CMD integration"
        ;;
    "ui")
        CMD="$CMD ui"
        ;;
    "all")
        CMD="$CMD all"
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

# Show deprecation warning
print_deprecation "This script is deprecated. Please use 'python run_tests.py' instead."
print_warning "The shell interface will be removed in a future version."
echo ""

# Run the tests
print_status "Running $TEST_TYPE tests..."
print_status "Command: $CMD"

if eval $CMD; then
    print_success "Tests completed successfully!"
    
    if [[ "$COVERAGE" == true ]]; then
        print_status "Coverage report generated in htmlcov/"
    fi
    
    echo ""
    print_deprecation "Consider migrating to the Python interface for better features:"
    echo "  python run_tests.py $TEST_TYPE"
    if [[ "$DOCKER_MODE" == true ]]; then
        echo "  python run_tests.py --docker $TEST_TYPE"
    fi
    if [[ "$COVERAGE" == true ]]; then
        echo "  python run_tests.py --coverage $TEST_TYPE"
    fi
else
    print_error "Tests failed!"
    echo ""
    print_deprecation "Consider using the Python interface for better error reporting:"
    echo "  python run_tests.py --debug $TEST_TYPE"
    exit 1
fi
