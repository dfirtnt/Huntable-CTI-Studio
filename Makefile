# Makefile for CTIScraper test suite

.PHONY: test-up test-down test test-unit test-integration test-ui test-e2e test-docs

# Start test containers
test-up:
	@echo "Starting test containers..."
	@./scripts/test_setup.sh

# Stop test containers
test-down:
	@echo "Stopping test containers..."
	@./scripts/test_teardown.sh

# Run all tests
test: test-up
	@echo "Running all tests..."
	@./scripts/run_tests.sh
	@$(MAKE) test-down

# Run unit tests (stateless)
test-unit:
	@./scripts/run_tests.sh tests/services/ tests/utils/ -m "not integration"

# Run integration tests (stateful, requires containers)
test-integration: test-up
	@./scripts/run_tests.sh tests/integration/ -m integration
	@$(MAKE) test-down

# Run UI tests
test-ui:
	@./scripts/run_tests.sh tests/ui/ -m ui

# Run E2E tests (TypeScript Playwright)
test-e2e:
	@npm test -- tests/playwright/workflow_full.spec.ts tests/playwright/eval_workflow.spec.ts

# Run documentation tests
test-docs:
	@./scripts/run_tests.sh tests/docs/

# Clean test artifacts
test-clean:
	@rm -rf test-results/ htmlcov/ .pytest_cache/ __pycache__/
	@find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

# Full test suite with cleanup
test-all: test-clean test
	@echo "All tests completed"
