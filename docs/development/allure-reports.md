# Allure Reports

Allure Reports provides interactive, step-by-step test execution reports. `run_tests.py` enables Allure automatically for every category it runs (it passes `--alluredir` itself) and clears `allure-results/` at the start of each run, so reports regenerate per run rather than accumulating.

## Setup

### Dependencies
Allure is included in test dependencies (`requirements-test.txt`):
```
allure-pytest>=2.13.0
```

### Configuration
<!-- AUDIT: Accuracy -- 2026-06-22: --alluredir was removed from the global pyproject addopts (forcing it globally made every ad-hoc pytest run accumulate allure-results/ unbounded, filling the disk). run_tests.py now adds it per run and clears the dir at start. -->
Allure is **not** wired into the global pytest `addopts`. Instead, `run_tests.py`
adds `--alluredir=allure-results` itself for each category it runs, and clears the
directory at the start of every run (`tests_runner.runner._clear_directory_contents`).
A bare `pytest <path>` therefore writes **no** Allure results unless you pass
`--alluredir` explicitly:
```bash
python3 -m pytest tests/ --alluredir=allure-results
```

## Running Tests

```bash
# Run all tests with Allure results
python3 run_tests.py all

# Run specific test categories
python3 run_tests.py unit
python3 run_tests.py integration
python3 run_tests.py ui
```

## Viewing Reports

### Containerized (Recommended)
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

### Local (Host)
```bash
# Install Allure commandline tool (one-time setup)
# macOS:
brew install allure

# Linux:
wget https://github.com/allure-framework/allure2/releases/download/2.24.1/allure-2.24.1.tgz
tar -zxf allure-2.24.1.tgz
sudo mv allure-2.24.1 /opt/allure
sudo ln -s /opt/allure/bin/allure /usr/local/bin/allure

# Serve interactive report
allure serve allure-results

# Or generate static HTML
allure generate allure-results --clean -o allure-report
allure open allure-report
```

## Output Structure

```
allure-results/
+-- *.json                    # Individual test results
+-- attachments/              # Screenshots, logs, custom data
```

Key data captured per test: name, status, duration, steps, attachments, labels, parameters, execution history.

## Project-Specific Usage

### ML/AI Test Visualization

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

### UI Test Screenshots

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

### Threat Intelligence Context

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

## Troubleshooting

### Allure Command Not Found
```bash
# macOS
brew install allure

# Linux (manual)
wget https://github.com/allure-framework/allure2/releases/download/2.24.1/allure-2.24.1.tgz
tar -zxf allure-2.24.1.tgz
sudo mv allure-2.24.1 /opt/allure
sudo ln -s /opt/allure/bin/allure /usr/local/bin/allure
```

### Empty Allure Results
```bash
# Ensure tests ran with --alluredir flag
python3 -m pytest tests/ --alluredir=allure-results

# Check directory exists
ls -la allure-results/
```

### Report Generation Issues
```bash
# Clean and regenerate
rm -rf allure-results/ allure-report/
python3 run_tests.py all
allure generate allure-results --clean -o allure-report
```

_Last updated: 2026-06-22_
_Last reviewed: 2026-06-22_
