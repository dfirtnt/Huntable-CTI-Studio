#!/bin/bash
# ML Feedback Feature Tests - Essential regression prevention tests
# This script runs the 3 critical tests for ML feedback features

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if we're in the right directory
if [[ ! -f "pytest.ini" ]]; then
    print_error "pytest.ini not found. Please run this script from the project root."
    exit 1
fi

print_status "Running ML Feedback Feature Tests..."
print_status "These tests prevent regression in the new ML feedback features."

# Test 1: Huntable Probability Calculation (Most Critical)
print_status "Test 1: Huntable Probability Calculation"
if docker exec cti_web python -m pytest tests/integration/test_huntable_probability.py -v; then
    print_success "✓ Huntable probability calculation tests passed"
else
    print_error "✗ Huntable probability calculation tests failed"
    exit 1
fi

# Test 2: Feedback Comparison API Contract
print_status "Test 2: Feedback Comparison API Contract"
if docker exec cti_web python -m pytest tests/api/test_ml_feedback.py::TestMLFeedbackAPI::test_feedback_comparison_api_contract -v; then
    print_success "✓ Feedback comparison API contract tests passed"
else
    print_error "✗ Feedback comparison API contract tests failed"
    exit 1
fi

# Test 3: Model Retraining Integration
print_status "Test 3: Model Retraining Integration"
if docker exec cti_web python -m pytest tests/integration/test_retraining_integration.py::TestModelRetrainingIntegration::test_retraining_creates_new_version -v; then
    print_success "✓ Model retraining integration tests passed"
else
    print_error "✗ Model retraining integration tests failed"
    exit 1
fi

print_success "All ML Feedback Feature Tests Passed!"
print_status "The critical ML feedback features are working correctly."
print_status "These tests will catch regressions in future development."
