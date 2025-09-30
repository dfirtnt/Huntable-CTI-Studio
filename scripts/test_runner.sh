#!/bin/bash
# Test runner script for CTI Scraper

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TEST_SUITE="light"
VERBOSE=false
COVERAGE=false
PARALLEL=1

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
    echo "Usage: $0 [OPTIONS] [TEST_SUITE]"
    echo ""
    echo "Test suites:"
    echo "  light     - Lightweight integration tests (default)"
    echo "  full      - Full integration tests (requires Docker)"
    echo "  unit      - Unit tests only"
    echo "  critical  - Critical path tests"
    echo "  all       - All tests"
    echo ""
    echo "Options:"
    echo "  -v, --verbose    Verbose output"
    echo "  -c, --coverage   Generate coverage report"
    echo "  -p, --parallel N Number of parallel workers"
    echo "  -h, --help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 light --verbose"
    echo "  $0 full --coverage"
    echo "  $0 unit --parallel 4"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -p|--parallel)
            PARALLEL="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        light|full|unit|critical|all)
            TEST_SUITE="$1"
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
if [[ ! -f "pytest.ini" ]]; then
    print_error "pytest.ini not found. Please run this script from the project root."
    exit 1
fi

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    print_warning "No virtual environment detected. Consider using a virtual environment."
fi

# Install test dependencies if requirements-test.txt exists
if [[ -f "requirements-test.txt" ]]; then
    print_status "Installing test dependencies..."
    pip install -r requirements-test.txt
fi

# Build command
CMD="python tests/run_lightweight_tests.py $TEST_SUITE"

if [[ "$VERBOSE" == true ]]; then
    CMD="$CMD --verbose"
fi

if [[ "$COVERAGE" == true ]]; then
    CMD="$CMD --coverage"
fi

if [[ "$PARALLEL" -gt 1 ]]; then
    CMD="$CMD --parallel $PARALLEL"
fi

# Run the tests
print_status "Running $TEST_SUITE tests..."
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
