# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in CTI Scraper, please follow these steps:

### 1. **DO NOT** create a public GitHub issue
Security vulnerabilities should be reported privately to prevent exploitation.

### 2. Email Security Team
Send details to: `security@cti-scraper.org` (replace with actual email)

Include the following information:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### 3. Response Timeline
- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Within 30 days (depending on complexity)

### 4. Responsible Disclosure
We follow responsible disclosure practices:
- We will acknowledge receipt of your report
- We will work with you to understand and resolve the issue
- We will credit you in our security advisories (unless you prefer to remain anonymous)
- We will not take legal action against security researchers acting in good faith

## Security Best Practices

### For Users
- Keep CTI Scraper updated to the latest version
- Use strong, unique passwords for database and Redis
- Enable HTTPS in production environments
- Regularly rotate API keys and secrets
- Monitor logs for suspicious activity

### For Developers
- Never commit secrets or API keys to the repository
- Use environment variables for sensitive configuration
- Validate all user inputs
- Implement proper authentication and authorization
- Follow secure coding practices

## Security Features

CTI Scraper includes several security features:

- **Input Validation**: All user inputs are validated and sanitized
- **SQL Injection Protection**: Uses parameterized queries
- **XSS Prevention**: Output encoding and CSP headers
- **Rate Limiting**: API rate limiting to prevent abuse
- **CORS Configuration**: Proper cross-origin resource sharing setup
- **Security Headers**: Comprehensive security headers implementation

## Dependencies

We regularly update dependencies and monitor for security vulnerabilities:
- Automated dependency scanning in CI/CD pipeline
- Regular security audits using `bandit` and `safety`
- Container vulnerability scanning with Trivy

## Security Updates

Security updates are released as:
- **Critical**: Immediate patch release
- **High**: Within 7 days
- **Medium/Low**: Next scheduled release

## Contact

For security-related questions or concerns:
- Email: `security@cti-scraper.org`
- PGP Key: [Available upon request]

---

**Thank you for helping keep CTI Scraper secure!**