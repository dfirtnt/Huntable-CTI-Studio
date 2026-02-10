# Python Version Requirements

## Current Status (2026-02-10)

**Recommended:** Python 3.12.x

**Why not 3.14+?**
- Langfuse SDK has pydantic v1/v2 compatibility issues with Python 3.14.2
- Error: `pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"`
- Affects test collection for any tests importing langfuse

## Version Compatibility Matrix

| Python Version | Status | Notes |
|----------------|--------|-------|
| 3.9.6 | ✅ Supported | ML venv only (specific library requirements) |
| 3.11.x | ✅ Supported | Docker standard, production |
| 3.12.x | ✅ **Recommended** | Local development, testing |
| 3.13.x | ⚠️ Not tested | May work but not validated |
| 3.14.x | ❌ Blocked | Langfuse/pydantic compatibility issues |

## Migration Notes

If you encounter pydantic errors with Python 3.14+:

```bash
# Remove existing venv
rm -rf .venv

# Install Python 3.12
brew install python@3.12

# Create new venv with Python 3.12
/opt/homebrew/bin/python3.12 -m venv .venv

# Reinstall dependencies
.venv/bin/pip3 install --upgrade pip setuptools wheel
.venv/bin/pip3 install -r requirements.txt
.venv/bin/pip3 install -r requirements-test.txt
```

## Docker

Docker containers use Python 3.11 and are not affected by this issue. This only impacts local development environments.

## Future

Monitor langfuse SDK updates for Python 3.14 compatibility:
- https://github.com/langfuse/langfuse-python/issues
