# GitHub Actions CI/CD Fix Guide

## ✅ ISSUE RESOLVED

**Problem**: GitHub Actions workflow failing with `ERROR: No matching distribution found for locust==3.0.0`

**Root Cause**: `locust==3.0.0` doesn't exist. Latest stable version is `2.40.1`

**Solution**: Updated `requirements-test.txt` to use `locust==2.40.1`

## How to Avoid This in the Future 🔧

### 1. Always Verify Package Versions
```bash
# Check if a package version exists
pip install --dry-run package==version

# Search PyPI for available versions
pip index versions package
```

### 2. Use Latest Stable Versions
```bash
# Install latest stable version
pip install package

# Pin to latest stable
pip freeze | grep package
```

### 3. Test Dependencies Locally
```bash
# Test requirements before pushing
pip install -r requirements-test.txt

# Or test in Docker
docker exec cti_web pip install -r /app/requirements-test.txt
```

### 4. Check GitHub Actions Logs
- Go to your repository → Actions tab
- Click on failed workflow
- Look for specific error messages
- Common errors:
  - `No matching distribution found` = version doesn't exist
  - `Package not found` = package name is wrong
  - `Version conflict` = dependency incompatibility

## Common Dependency Issues 🚨

### Version Doesn't Exist
```bash
# ❌ Wrong
package==999.0.0

# ✅ Correct
package==2.40.1
```

### Package Name Wrong
```bash
# ❌ Wrong
beautiful-soup4==4.13.5

# ✅ Correct
beautifulsoup4==4.13.5
```

### Dependency Conflicts
```bash
# Check for conflicts
pip check

# Resolve conflicts
pip install --upgrade conflicting-package
```

## Quick Fix Workflow 🚀

1. **Identify Error**: Check GitHub Actions logs
2. **Test Locally**: `pip install --dry-run package==version`
3. **Find Correct Version**: `pip index versions package`
4. **Update Requirements**: Edit requirements file
5. **Test Fix**: `pip install -r requirements.txt`
6. **Commit & Push**: `git add . && git commit -m "fix: ..." && git push`

## Monitoring Dependencies 📊

### Regular Updates
```bash
# Update all packages
pip install --upgrade -r requirements.txt

# Check for security vulnerabilities
pip install safety
safety check -r requirements.txt
```

### Automated Checks
- Enable Dependabot alerts in GitHub
- Use `safety` package for vulnerability scanning
- Set up pre-commit hooks for dependency validation

## Latest Fix: Deprecated GitHub Actions ✅

**Problem**: GitHub Actions failing due to deprecated `actions/upload-artifact@v3`

**Solution**: Updated all deprecated actions to latest versions:

### Updated Actions in `.github/workflows/ci.yml`:
- `actions/upload-artifact@v3` → `actions/upload-artifact@v4`
- `actions/cache@v3` → `actions/cache@v4`
- `codecov/codecov-action@v3` → `codecov/codecov-action@v4`
- `docker/setup-buildx-action@v2` → `docker/setup-buildx-action@v3`

### Already Updated in `.github/workflows/test.yml`:
- ✅ `actions/upload-artifact@v4` (already correct)

## Common Deprecated Actions to Watch For 🚨

### Recently Deprecated (2024):
- `actions/upload-artifact@v3` → `actions/upload-artifact@v4`
- `actions/download-artifact@v3` → `actions/download-artifact@v4`
- `actions/cache@v3` → `actions/cache@v4`

### Check for Deprecations:
```bash
# Check workflow files for deprecated actions
grep -r "actions/" .github/workflows/
```

### Update Pattern:
```yaml
# ❌ Deprecated
- uses: actions/upload-artifact@v3

# ✅ Current
- uses: actions/upload-artifact@v4
```

Your CI/CD pipeline should now work correctly! 🎉
