# Security Audit Report
**Date**: 2025-01-29  
**Project**: CTIScraper  
**Version**: 4.0.0

## Executive Summary

This security audit identified **8 critical issues**, **5 high-severity issues**, and **3 medium-severity issues** requiring immediate attention. The application lacks authentication/authorization, has permissive CORS configuration, and contains XSS vulnerabilities in template rendering.

---

## Critical Issues (Priority: Immediate Fix Required)

### 1. **No Authentication/Authorization System**
**Severity**: 🔴 CRITICAL  
**Location**: Entire application  
**Impact**: Unauthorized access to all endpoints and data

**Findings**:
- No authentication middleware found
- All API endpoints are publicly accessible
- No user session management
- No role-based access control (RBAC)

**Recommendations**:
```python
# Add authentication middleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # Implement token validation
    if not validate_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid authentication")
    return credentials.credentials
```

**Action Items**:
- [ ] Implement JWT-based authentication
- [ ] Add session management
- [ ] Implement role-based access control
- [ ] Protect sensitive endpoints (e.g., `/api/workflow`, `/api/sources`)

---

### 2. **Permissive CORS Configuration**
**Severity**: 🔴 CRITICAL  
**Location**: `src/web/modern_main.py:138`  
**Impact**: Allows any origin to make authenticated requests

**Current Code**:
```136:142:src/web/modern_main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Issue**: `allow_origins=["*"]` with `allow_credentials=True` is insecure and can lead to CSRF attacks.

**Recommendations**:
```python
# Environment-based CORS configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8001").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Specific origins only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
```

**Action Items**:
- [ ] Replace wildcard with specific allowed origins
- [ ] Use environment variables for production configuration
- [ ] Document allowed origins in deployment guide

---

### 3. **XSS Vulnerability in Template Rendering**
**Severity**: 🔴 CRITICAL  
**Location**: `src/web/templates/article_detail.html:462`  
**Impact**: Stored XSS via article content

**Current Code**:
```462:462:src/web/templates/article_detail.html
<div id="article-content" class="...">{{ article.content|highlight_keywords(article.article_metadata)|safe }}</div>
```

**Issue**: The `|safe` filter disables auto-escaping, allowing malicious HTML/JavaScript in article content to execute.

**Recommendations**:
```python
# Option 1: Remove |safe and escape content
{{ article.content|highlight_keywords(article.article_metadata)|e }}

# Option 2: Sanitize HTML before rendering
from bleach import clean

def sanitize_html(content: str) -> str:
    return clean(
        content,
        tags=['span', 'div', 'p', 'br'],
        attributes={'span': ['class', 'title']},
        strip=True
    )
```

**Action Items**:
- [ ] Remove `|safe` filter or implement HTML sanitization
- [ ] Use `bleach` or `html-sanitizer` library
- [ ] Validate article content on ingestion
- [ ] Add Content Security Policy (CSP) headers

---

### 4. **API Key Logging**
**Severity**: 🔴 CRITICAL  
**Location**: `src/web/routes/ai.py:2971-2981`  
**Impact**: API keys exposed in logs

**Current Code**:
```2971:2981:src/web/routes/ai.py
logger.info(
    f"🔍 DEBUG SIGMA: api_key source: {api_key_source}, type: {type(api_key_raw)}, length: {len(api_key_raw) if isinstance(api_key_raw, str) else 'N/A'}, ends_with: ...{api_key_raw[-4:] if isinstance(api_key_raw, str) and len(api_key_raw) >= 4 else 'N/A'}"
)
```

**Issue**: API keys are logged with partial exposure (last 4 characters), which could be used for enumeration.

**Recommendations**:
```python
# Mask API keys completely
def mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}...{key[-2:]}"

logger.info(f"API key source: {api_key_source}, masked: {mask_api_key(api_key_raw)}")
```

**Action Items**:
- [ ] Remove API key logging in production
- [ ] Implement key masking utility
- [ ] Use environment variable for debug logging
- [ ] Audit all log statements for sensitive data

---

### 5. **Docker Socket Mount**
**Severity**: 🔴 CRITICAL  
**Location**: `docker-compose.yml:94`  
**Impact**: Container escape and host system compromise

**Current Code**:
```94:94:docker-compose.yml
- /var/run/docker.sock:/var/run/docker.sock
```

**Issue**: Mounting Docker socket gives container full control over the host Docker daemon.

**Recommendations**:
- Remove socket mount if not required
- If required, use Docker-in-Docker (DinD) or Docker API with proper authentication
- Restrict socket permissions: `chmod 660 /var/run/docker.sock`

**Action Items**:
- [ ] Remove socket mount or document why it's required
- [ ] Implement alternative solution if Docker access is needed
- [ ] Add security documentation for production deployment

---

### 6. **TrustedHostMiddleware with Wildcard**
**Severity**: 🔴 CRITICAL  
**Location**: `src/web/modern_main.py:144`  
**Impact**: Host header injection attacks

**Current Code**:
```144:144:src/web/modern_main.py
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
```

**Issue**: `allowed_hosts=["*"]` disables host validation, allowing host header injection.

**Recommendations**:
```python
# Environment-based host validation
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
```

**Action Items**:
- [ ] Replace wildcard with specific allowed hosts
- [ ] Use environment variables for configuration
- [ ] Document host configuration in deployment guide

---

### 7. **No Rate Limiting on API Endpoints**
**Severity**: 🔴 CRITICAL  
**Location**: Application-wide  
**Impact**: DoS attacks, API abuse, resource exhaustion

**Findings**:
- No rate limiting middleware found
- API endpoints can be called unlimited times
- No protection against brute force attacks

**Recommendations**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.post("/api/articles/{id}/generate-sigma")
@limiter.limit("10/minute")
async def api_generate_sigma(...):
    ...
```

**Action Items**:
- [ ] Implement rate limiting using `slowapi` or `fastapi-limiter`
- [ ] Configure different limits for different endpoints
- [ ] Add rate limit headers to responses
- [ ] Document rate limits in API documentation

---

### 8. **PDF Upload Security Issues**
**Severity**: 🔴 CRITICAL  
**Location**: `src/web/routes/pdf.py:22-271`  
**Impact**: Malicious file uploads, path traversal, DoS

**Issues**:
1. **File type validation**: Only checks extension, not MIME type
2. **No virus scanning**: Malicious PDFs can be uploaded
3. **Temporary file handling**: Files created with predictable names
4. **No file content validation**: PDFs with embedded scripts can be processed

**Recommendations**:
```python
import magic  # python-magic library

# Validate MIME type
file_content = await file.read()
mime_type = magic.from_buffer(file_content, mime=True)
if mime_type != "application/pdf":
    raise HTTPException(status_code=400, detail="Invalid file type")

# Use secure temporary file
import tempfile
import os

temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf", dir="/tmp/secure_uploads")
try:
    with os.fdopen(temp_fd, "wb") as f:
        f.write(file_content)
    # Process file
finally:
    os.unlink(temp_path)
```

**Action Items**:
- [ ] Add MIME type validation
- [ ] Implement virus scanning (ClamAV integration)
- [ ] Use secure temporary file handling
- [ ] Validate PDF structure before processing
- [ ] Add file size limits per user/IP

---

## High-Severity Issues

### 9. **SQL Injection Risk (Low - ORM Used)**
**Severity**: 🟠 HIGH  
**Location**: Codebase-wide  
**Status**: ✅ **MITIGATED** - SQLAlchemy ORM used correctly

**Findings**:
- SQLAlchemy ORM is used throughout (good)
- Parameterized queries are standard
- `QuerySafetyValidator` exists but not used everywhere

**Recommendations**:
- Continue using ORM for all queries
- Audit any raw SQL queries
- Use `QuerySafetyValidator` for any dynamic SQL

---

### 10. **Missing Content Security Policy (CSP)**
**Severity**: 🟠 HIGH  
**Location**: `src/web/modern_main.py`  
**Impact**: XSS attacks, data exfiltration

**Recommendations**:
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:;"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```

**Action Items**:
- [ ] Add CSP headers
- [ ] Configure CSP for production
- [ ] Test CSP with application functionality

---

### 11. **Secrets in Environment Variables (Good Practice)**
**Severity**: 🟠 HIGH  
**Location**: `docker-compose.yml`  
**Status**: ✅ **GOOD** - Secrets use environment variables

**Findings**:
- Secrets are passed via environment variables (correct)
- No hardcoded credentials found in code
- `.env` files should be in `.gitignore` (verify)

**Recommendations**:
- Use secrets management (AWS Secrets Manager, HashiCorp Vault)
- Rotate secrets regularly
- Document secret requirements
- Verify `.env` is in `.gitignore`

---

### 12. **No Input Validation on Some Endpoints**
**Severity**: 🟠 HIGH  
**Location**: Various API endpoints  
**Impact**: Injection attacks, data corruption

**Findings**:
- Some endpoints accept raw JSON without validation
- Article ID parameters not always validated
- File uploads have basic validation but could be improved

**Recommendations**:
```python
from pydantic import BaseModel, validator, Field

class ArticleRequest(BaseModel):
    article_id: int = Field(..., gt=0, description="Article ID must be positive")
    
    @validator('article_id')
    def validate_article_id(cls, v):
        if v <= 0:
            raise ValueError('Article ID must be positive')
        return v
```

**Action Items**:
- [ ] Add Pydantic models for all request bodies
- [ ] Validate all path parameters
- [ ] Add input sanitization
- [ ] Document validation rules

---

### 13. **Error Information Disclosure**
**Severity**: 🟠 HIGH  
**Location**: Exception handlers  
**Impact**: Information leakage to attackers

**Current Code**:
```165:173:src/web/modern_main.py
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: HTTPException):
    """Handle 500 errors."""
    logger.error("Internal server error: %s", exc)
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Internal server error"},
        status_code=500,
    )
```

**Issue**: Stack traces may be exposed in development mode.

**Recommendations**:
```python
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: HTTPException):
    logger.error("Internal server error: %s", exc, exc_info=True)
    
    # Don't expose details in production
    if ENVIRONMENT == "production":
        error_message = "Internal server error"
    else:
        error_message = str(exc)
    
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": error_message},
        status_code=500,
    )
```

**Action Items**:
- [ ] Hide error details in production
- [ ] Log full errors server-side only
- [ ] Use generic error messages for users
- [ ] Add error tracking (Sentry, etc.)

---

## Medium-Severity Issues

### 14. **Dependency Vulnerabilities**
**Severity**: 🟡 MEDIUM  
**Location**: `requirements.txt`  
**Status**: ⚠️ **NEEDS AUDIT**

**Action Items**:
- [ ] Run `pip-audit` to check for known vulnerabilities
- [ ] Run `safety check` for additional checks
- [ ] Update vulnerable dependencies
- [ ] Add automated dependency scanning to CI/CD

**Command**:
```bash
pip install pip-audit safety
pip-audit
safety check
```

---

### 15. **Missing HTTPS Enforcement**
**Severity**: 🟡 MEDIUM  
**Location**: Application configuration  
**Impact**: Man-in-the-middle attacks

**Findings**:
- Nginx configuration has HTTPS support
- Application doesn't enforce HTTPS redirect
- No HSTS headers in application (present in Nginx)

**Recommendations**:
- Add HTTPS redirect middleware
- Enforce HTTPS in production
- Use secure cookies
- Add HSTS headers

---

### 16. **Session Management**
**Severity**: 🟡 MEDIUM  
**Location**: Application-wide  
**Impact**: Session hijacking, fixation attacks

**Findings**:
- No session management implemented
- No secure cookie configuration
- No session timeout

**Recommendations**:
- Implement secure session management
- Use HttpOnly, Secure, SameSite cookies
- Implement session timeout
- Add CSRF tokens

---

## Positive Security Findings

### ✅ Good Practices Found

1. **SQL Injection Protection**: SQLAlchemy ORM used correctly
2. **Secrets Management**: Environment variables used (not hardcoded)
3. **Non-Root Docker User**: Containers run as non-root (`cti_user`)
4. **Input Validation**: Some endpoints use Pydantic models
5. **Security Headers in Nginx**: X-Frame-Options, X-Content-Type-Options present
6. **Query Safety Validator**: Exists for dynamic SQL (though not used everywhere)
7. **File Size Limits**: PDF uploads limited to 50MB
8. **Docker Health Checks**: Health checks configured for services

---

## Recommendations Summary

### Immediate Actions (Critical)
1. ✅ Implement authentication/authorization system
2. ✅ Fix CORS configuration (remove wildcard)
3. ✅ Fix XSS vulnerability (remove `|safe` or sanitize)
4. ✅ Remove API key logging
5. ✅ Remove or secure Docker socket mount
6. ✅ Fix TrustedHostMiddleware configuration
7. ✅ Implement rate limiting
8. ✅ Improve PDF upload security

### Short-Term Actions (High Priority)
1. Add Content Security Policy headers
2. Improve input validation
3. Fix error information disclosure
4. Audit dependencies for vulnerabilities

### Long-Term Actions (Medium Priority)
1. Implement session management
2. Enforce HTTPS
3. Add security monitoring and logging
4. Implement security testing in CI/CD

---

## Security Testing Recommendations

1. **Penetration Testing**: Engage security professionals for penetration testing
2. **Dependency Scanning**: Automate dependency vulnerability scanning
3. **SAST**: Implement static application security testing
4. **DAST**: Implement dynamic application security testing
5. **Security Code Reviews**: Mandatory security reviews for all changes

---

## Compliance Considerations

- **OWASP Top 10**: Address all OWASP Top 10 vulnerabilities
- **CWE**: Review Common Weakness Enumeration for additional issues
- **GDPR**: If handling EU data, ensure GDPR compliance
- **SOC 2**: Consider SOC 2 compliance for enterprise deployments

---

## Conclusion

The application has a solid foundation with good practices (ORM usage, environment variables, non-root containers) but requires immediate attention to critical security issues, particularly authentication, CORS, and XSS vulnerabilities. Priority should be given to implementing authentication and fixing the identified critical vulnerabilities before production deployment.

**Overall Security Rating**: 🔴 **NEEDS IMMEDIATE ATTENTION**

---

## Next Steps

1. Review and prioritize findings
2. Create security fix tickets
3. Implement fixes starting with critical issues
4. Re-audit after fixes are implemented
5. Establish ongoing security review process


