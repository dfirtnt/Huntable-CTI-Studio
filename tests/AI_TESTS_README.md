# AI Assistant Priority 1 Tests

This directory contains comprehensive tests for AI Assistant features, implementing the Priority 1 testing gaps identified in the analysis.

## Test Structure

### 1. UI Tests (`tests/ui/test_ai_assistant_ui.py`)
Tests the AI Assistant user interface components:

- **AI Assistant Button**: Visibility, styling, and functionality
- **Modal Interface**: Opening, closing, and content display
- **Content Size Limits**: Validation and warnings for large articles
- **Model Selection**: Settings persistence and UI updates
- **SIGMA Rules**: Availability based on article classification
- **Custom Prompt**: Modal functionality and form handling
- **Error Handling**: API failures and user feedback
- **Loading States**: Progress indicators and user feedback
- **Accessibility**: Keyboard navigation and screen reader support
- **Threat Score Warnings**: Low score notifications for SIGMA rules

### 2. Cross-Model Integration Tests (`tests/integration/test_ai_cross_model_integration.py`)
Tests integration between different AI models:

- **Model Switching**: ChatGPT ↔ Anthropic ↔ Ollama
- **Fallback Logic**: Handling model failures and automatic fallbacks
- **Content Size Limits**: Model-specific content restrictions
- **Feature Support**: Model-specific capabilities and limitations
- **Concurrent Requests**: Multiple models processing simultaneously
- **Performance Comparison**: Response times and quality differences
- **Configuration Validation**: Model setup and parameter validation
- **Error Handling**: Consistent error responses across models

### 3. Real API Integration Tests (`tests/integration/test_ai_real_api_integration.py`)
Tests actual API calls to AI services:

- **OpenAI GPT-4o**: Real API calls with authentication
- **Anthropic Claude**: Real API calls with rate limiting
- **Ollama Local**: Local model execution and validation
- **GPT-4o Optimizer**: Content filtering and cost optimization
- **IOC Extractor**: Real IOC extraction and validation
- **Rate Limiting**: API quota and timeout handling
- **Error Responses**: Invalid keys, network failures, timeouts
- **End-to-End Workflow**: Complete AI processing pipeline
- **Cost Tracking**: Token usage and cost estimation

## Running the Tests

### Quick Start
```bash
# Run all AI Assistant tests
python tests/run_ai_tests.py

# Run specific test types
python tests/run_ai_tests.py --type ui
python tests/run_ai_tests.py --type integration
python tests/run_ai_tests.py --type all

# Run with coverage
python tests/run_ai_tests.py --coverage

# Skip real API tests (faster, no API keys needed)
python tests/run_ai_tests.py --skip-real-api
```

### Manual Execution
```bash
# UI tests only
pytest tests/ui/test_ai_assistant_ui.py -v -m "ui and ai"

# Integration tests only
pytest tests/integration/test_ai_cross_model_integration.py -v -m "integration and ai"

# Real API tests (requires API keys)
pytest tests/integration/test_ai_real_api_integration.py -v -m "integration and ai"

# All AI tests
pytest -v -m "ai" tests/ui/test_ai_assistant_ui.py tests/integration/test_ai_cross_model_integration.py tests/integration/test_ai_real_api_integration.py
```

## Environment Setup

### Required Environment Variables
```bash
# For real API integration tests
export OPENAI_API_KEY="sk-your-openai-key"
export ANTHROPIC_API_KEY="sk-ant-your-anthropic-key"

# Optional: Custom Ollama endpoint
export OLLAMA_ENDPOINT="http://localhost:11434"

# For UI tests
export CTI_SCRAPER_URL="http://localhost:8001"
```

### Docker Environment
```bash
# Start the application
docker-compose up -d

# Run tests against running application
python tests/run_ai_tests.py --type ui
```

### Local Development
```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run tests in virtual environment
source venv-test/bin/activate
python tests/run_ai_tests.py
```

## Test Categories

### Markers
- `@pytest.mark.ai` - AI-related tests
- `@pytest.mark.ui` - User interface tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests (real API calls)

### Test Types
- **Unit Tests**: Individual component testing
- **Integration Tests**: Cross-component interaction testing
- **End-to-End Tests**: Complete workflow testing
- **Performance Tests**: Response time and throughput testing
- **Error Handling Tests**: Failure scenario testing

## Coverage Areas

### ✅ Covered (Priority 1)
- [x] AI Assistant UI functionality
- [x] Modal interactions and user experience
- [x] Content size limit validation
- [x] Model selection and persistence
- [x] Cross-model integration and fallbacks
- [x] Real API integration with error handling
- [x] SIGMA rules availability logic
- [x] Custom prompt interface
- [x] Loading states and user feedback
- [x] Accessibility features

### 🔄 Partially Covered
- [ ] Performance benchmarking
- [ ] Load testing with multiple users
- [ ] Security testing (API key handling)
- [ ] Cost optimization validation

### ❌ Not Covered (Future Priorities)
- [ ] Advanced error recovery scenarios
- [ ] Multi-language content handling
- [ ] Complex workflow edge cases
- [ ] Integration with external threat feeds

## Test Data

### Sample Content
Tests use realistic threat intelligence content including:
- APT29 campaign descriptions
- PowerShell and LOLBAS techniques
- Registry persistence mechanisms
- IOC examples (IPs, domains, hashes, emails)
- File paths and process relationships

### Mock Responses
Comprehensive mock responses for:
- OpenAI GPT-4o analysis
- Anthropic Claude responses
- Ollama SIGMA rule generation
- Error scenarios and edge cases

## Troubleshooting

### Common Issues

**UI Tests Failing**
```bash
# Ensure application is running
docker-compose up -d

# Check application URL
export CTI_SCRAPER_URL="http://localhost:8001"
```

**API Tests Failing**
```bash
# Check API keys
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Skip real API tests
python tests/run_ai_tests.py --skip-real-api
```

**Ollama Tests Failing**
```bash
# Check Ollama installation
ollama --version

# Check available models
ollama list

# Install test model
ollama pull llama2
```

### Debug Mode
```bash
# Run with verbose output
python tests/run_ai_tests.py --verbose

# Run single test
pytest tests/ui/test_ai_assistant_ui.py::TestAIAssistantUI::test_ai_assistant_button_visible -v -s
```

## Contributing

### Adding New Tests
1. Follow existing test structure and naming conventions
2. Add appropriate markers (`@pytest.mark.ai`, etc.)
3. Include comprehensive docstrings
4. Add to the appropriate test file or create new one
5. Update this README with new coverage areas

### Test Best Practices
- Use descriptive test names
- Include setup and teardown logic
- Mock external dependencies
- Test both success and failure scenarios
- Include performance considerations
- Document test data and expected outcomes

## Metrics and Reporting

### Coverage Reports
```bash
# Generate HTML coverage report
python tests/run_ai_tests.py --coverage

# View report
open htmlcov/ai_tests/index.html
```

### Test Results
- **UI Tests**: ~15 test cases
- **Integration Tests**: ~20 test cases  
- **Real API Tests**: ~10 test cases
- **Total**: ~45 comprehensive test cases

### Performance Benchmarks
- UI tests: < 30 seconds
- Integration tests: < 60 seconds
- Real API tests: < 120 seconds (depends on API response times)

## Future Enhancements

### Priority 2 Improvements
- [ ] Performance benchmarking suite
- [ ] Load testing with concurrent users
- [ ] Security testing for API key handling
- [ ] Cost optimization validation tests

### Priority 3 Enhancements
- [ ] Multi-language content testing
- [ ] Advanced error recovery scenarios
- [ ] Integration with external threat feeds
- [ ] Machine learning model validation tests
