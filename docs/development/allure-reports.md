# Allure Reports Integration Guide

## Overview

Huntable CTI Studio now includes Allure Reports integration for comprehensive test visualization and debugging. Allure provides interactive, step-by-step test execution reports that are particularly valuable for ML/AI testing, UI testing, and complex integration scenarios.

## Features

### 🎯 **Interactive Test Reports**
- **Step-by-step visualization**: See exactly what each test does
- **Rich attachments**: Screenshots, logs, and custom data
- **Historical tracking**: Compare test results over time
- **Filtering and search**: Find specific tests or failures quickly

### 🔍 **Huntable CTI Studio-specific benefits**
- **ML/AI Debugging**: Visualize AI inference steps and confidence scores
- **UI Test Screenshots**: Automatic Playwright screenshot capture on failures
- **Threat Intelligence Context**: Step-by-step IOC extraction and threat hunting
- **Integration Testing**: Detailed API call sequences and database operations

## Setup

### Dependencies
Allure is automatically installed with test dependencies:
```bash
allure-pytest>=2.13.0
```

### Configuration
Allure is enabled by default in `pytest.ini`:
```ini
addopts = 
    --alluredir=allure-results
```

## Usage

### Running Tests with Allure

#### 1. Standard Test Execution
```bash
# Run all tests with Allure reports
python3 run_tests.py --all

# Run specific test categories
python3 run_tests.py --unit
python3 run_tests.py --integration
python3 run_tests.py --ui
```

#### 2. Manual Test Execution
```bash
# Run tests with Allure results
python3 -m pytest tests/ -v --alluredir=allure-results

# Run specific test file
python3 -m pytest tests/test_utils.py -v --alluredir=allure-results
```

### Viewing Allure Reports

#### 1. Generate Report Data
```bash
# Run tests to generate Allure results
python3 run_tests.py --all
```

#### 2. Containerized Reports (Recommended)
```bash
# Start dedicated Allure container
./manage_allure.sh start

# Stop container
./manage_allure.sh stop

# View logs
./manage_allure.sh logs

# Check status
./manage_allure.sh status
```

Access reports at: `http://localhost:8080`

#### 3. Serve Interactive Reports (Host)
```bash
# Install Allure commandline tool (one-time setup)
# macOS: brew install allure
# Linux: See https://docs.qameta.io/allure/#_installing_a_commandline

# Serve reports locally
allure serve allure-results
```

This will:
- Generate HTML reports from JSON data
- Start a local web server
- Open the report in your browser (typically `http://localhost:random-port`)

#### 4. Generate Static Reports
```bash
# Generate static HTML report
allure generate allure-results --clean -o allure-report

# Open static report
allure open allure-report
```

## Output Structure

### Allure Results Directory (`allure-results/`)
Contains detailed test execution data in JSON format:

```
allure-results/
├── *.json                    # Individual test results
├── *.json                    # Test containers and fixtures
└── attachments/              # Screenshots, logs, custom data
```

### Key Data Points Captured
- **Test metadata**: Name, description, status, duration
- **Test steps**: Detailed execution steps
- **Attachments**: Screenshots, logs, custom files
- **Labels**: Test categories, suites, packages
- **Parameters**: Test parameters and environment info
- **History**: Test execution history and trends

## Huntable CTI Studio-specific features

### 1. ML/AI Test Visualization
Perfect for debugging AI inference and ML feedback tests:

```python
import allure

@allure.step("AI Model Inference")
def test_ai_inference():
    with allure.step("Load model"):
        model = load_ai_model()
    
    with allure.step("Process input"):
        result = model.predict(test_data)
    
    with allure.step("Validate confidence"):
        assert result.confidence > 0.8
```

### 2. UI Test Screenshots
Automatic screenshot capture for Playwright tests:

```python
import allure
from playwright.sync_api import Page

def test_ui_functionality(page: Page):
    with allure.step("Navigate to dashboard"):
        page.goto("/dashboard")
        allure.attach(page.screenshot(), name="Dashboard", attachment_type=allure.attachment_type.PNG)
    
    with allure.step("Verify elements"):
        assert page.locator(".status-indicator").is_visible()
```

### 3. Threat Intelligence Context
Rich visualization for IOC extraction and threat hunting:

```python
import allure

@allure.step("IOC Extraction")
def test_ioc_extraction():
    with allure.step("Extract IPs"):
        ips = extract_ips(sample_text)
        allure.attach(str(ips), name="Extracted IPs", attachment_type=allure.attachment_type.TEXT)
    
    with allure.step("Validate extraction"):
        assert len(ips) > 0
```

## Integration with Existing Tools

### Complementary Reporting Ecosystem
Allure works alongside existing Huntable CTI Studio reporting tools:

- **Duration Insights**: Performance analysis and bottleneck identification
- **Coverage Reports**: Code coverage analysis
- **HTML Reports**: Basic test execution reports
- **Allure Reports**: Detailed step-by-step visualization

### Usage Patterns
- **Performance Analysis**: Use duration insights for slow test identification
- **Detailed Debugging**: Use Allure for step-by-step failure analysis
- **Coverage Analysis**: Use coverage reports for code quality metrics
- **Quick Overview**: Use HTML reports for basic test status

## CI/CD Integration

### GitHub Actions
Allure reports are automatically integrated into the CI/CD pipeline:

```yaml
- name: Run Tests with Allure
  run: |
    python3 run_tests.py --all
    
- name: Generate Allure Report
  run: |
    allure generate allure-results --clean -o allure-report
    
- name: Upload Allure Report
  uses: actions/upload-artifact@v3
  with:
    name: allure-report
    path: allure-report/
```

### Docker Environment
```bash
# Run tests in Docker with Allure
docker exec cti_web python3 -m pytest tests/ --alluredir=allure-results

# Serve reports locally
allure serve allure-results
```

## Advanced Features

### Custom Attachments
Add custom data to test reports:

```python
import allure
import json

def test_with_custom_data():
    # Attach JSON data
    data = {"confidence": 0.95, "model": "gpt-4"}
    allure.attach(json.dumps(data, indent=2), name="Model Results", attachment_type=allure.attachment_type.JSON)
    
    # Attach text data
    allure.attach("Test execution log", name="Execution Log", attachment_type=allure.attachment_type.TEXT)
```

### Test Categorization
Organize tests with labels:

```python
import allure
import pytest

@pytest.mark.allure_label("component", "ml")
@pytest.mark.allure_label("severity", "critical")
def test_ml_inference():
    pass
```

### Step Decorators
Add detailed step information:

```python
import allure

@allure.step("Process threat intelligence data")
def process_threat_data(data):
    with allure.step("Validate input"):
        validate_input(data)
    
    with allure.step("Extract IOCs"):
        iocs = extract_iocs(data)
    
    return iocs
```

## Best Practices

### 1. Test Organization
- Use descriptive test names and step descriptions
- Group related tests with appropriate labels
- Add meaningful attachments for debugging

### 2. ML/AI Testing
- Capture model confidence scores
- Attach input/output data for debugging
- Visualize inference steps clearly

### 3. UI Testing
- Take screenshots at key interaction points
- Capture browser console logs
- Document user workflow steps

### 4. Integration Testing
- Show API call sequences
- Capture request/response data
- Document database operations

## Troubleshooting

### Common Issues

#### 1. Allure Command Not Found
```bash
# Install Allure commandline tool
# macOS
brew install allure

# Linux
wget https://github.com/allure-framework/allure2/releases/download/2.24.1/allure-2.24.1.tgz
tar -zxf allure-2.24.1.tgz
sudo mv allure-2.24.1 /opt/allure
sudo ln -s /opt/allure/bin/allure /usr/local/bin/allure
```

#### 2. Empty Allure Results
```bash
# Ensure tests are run with --alluredir flag
python3 -m pytest tests/ --alluredir=allure-results

# Check if allure-results directory exists
ls -la allure-results/
```

#### 3. Report Generation Issues
```bash
# Clean previous results
rm -rf allure-results/ allure-report/

# Regenerate reports
python3 run_tests.py --all
allure generate allure-results --clean -o allure-report
```

## Performance Considerations

### Report Size Management
- Allure reports can grow large with many tests
- Consider archiving old reports
- Use `--clean` flag when generating reports

### CI/CD Optimization
- Generate reports only for failed tests in CI
- Use static reports for artifact storage
- Consider report caching for large test suites

## Future Enhancements

- **Real-time Reporting**: Live test execution monitoring
- **Custom Dashboards**: Huntable CTI Studio-specific metrics
- **Integration with Monitoring**: Connect with external monitoring tools
- **Advanced Filtering**: Custom test categorization and filtering

## Summary

Allure Reports provide Huntable CTI Studio with:
- **Enhanced Debugging**: Step-by-step test visualization
- **ML/AI Focus**: Perfect for AI inference debugging
- **UI Testing**: Automatic screenshot capture
- **Threat Intelligence**: Rich context for security testing
- **Integration**: Seamless CI/CD pipeline integration

The combination of Allure Reports with Duration Insights creates a comprehensive testing ecosystem that provides both performance analysis and detailed debugging capabilities.
