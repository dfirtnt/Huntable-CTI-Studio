# Security Policy

## Supported Versions

We actively support the following versions of CTI Scraper:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in CTI Scraper, please follow these steps:

### 1. **DO NOT** create a public GitHub issue
Security vulnerabilities should be reported privately to prevent exploitation.

### 2. Email us directly
Send details to: `security@cti-scraper.dev` (replace with actual email)

Include the following information:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### 3. Response timeline
- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Resolution**: Depends on complexity, typically 30-90 days

### 4. What to expect
- We will acknowledge receipt of your report
- We will investigate and validate the vulnerability
- We will work on a fix and coordinate disclosure
- We will credit you in our security advisories (unless you prefer anonymity)

## Security Best Practices

### For Users
- Keep your installation updated
- Use strong passwords for database and Redis
- Regularly rotate API keys
- Monitor access logs
- Use HTTPS in production
- Keep dependencies updated

### For Developers
- Follow secure coding practices
- Validate all inputs
- Use parameterized queries
- Implement proper authentication
- Regular security audits
- Dependency vulnerability scanning

## Security Features

CTI Scraper includes several security features:

- **Environment-based configuration**: All secrets via environment variables
- **Input validation**: Comprehensive validation of all inputs
- **SQL injection protection**: Parameterized queries throughout
- **Rate limiting**: API rate limiting to prevent abuse
- **CORS protection**: Configurable CORS policies
- **Security headers**: Proper security headers in responses
- **Dependency scanning**: Regular security updates

## Security Updates

Security updates are released as:
- **Critical**: Immediate patch release
- **High**: Next minor release
- **Medium/Low**: Next major release

All security updates are documented in our [CHANGELOG](CHANGELOG.md).

## Responsible Disclosure

We follow responsible disclosure principles:
1. Report privately first
2. Allow reasonable time for fixes
3. Coordinate public disclosure
4. Credit researchers appropriately

## Contact

For security-related questions or concerns:
- Email: `security@cti-scraper.dev`
- PGP Key: Available upon request

---

**Note**: This security policy applies to the CTI Scraper project. Users are responsible for securing their own deployments and data.