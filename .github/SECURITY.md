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

### 2. Email Security Report
Send an email to: `security@ctiscraper.dev` (or your security contact email)

Include the following information:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Any suggested fixes or mitigations
- Your contact information

### 3. Response Timeline
- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Depends on severity and complexity

### 4. Vulnerability Severity Levels

| Severity | Response Time | Description |
|----------|---------------|-------------|
| **Critical** | 24 hours | Remote code execution, authentication bypass, data exposure |
| **High** | 72 hours | Privilege escalation, significant data leakage |
| **Medium** | 1 week | Information disclosure, denial of service |
| **Low** | 2 weeks | Minor security improvements |

## Security Best Practices

### For Users
- Keep your dependencies updated
- Use strong passwords for database and Redis
- Enable HTTPS in production
- Regularly review access logs
- Use environment variables for sensitive configuration

### For Developers
- Follow secure coding practices
- Validate all user inputs
- Use parameterized queries
- Implement proper authentication and authorization
- Regular security audits of dependencies

## Security Features

### Built-in Security Measures
- **Input Validation**: All user inputs are validated and sanitized
- **SQL Injection Protection**: Uses SQLAlchemy ORM with parameterized queries
- **Rate Limiting**: API endpoints have rate limiting enabled
- **CORS Protection**: Configurable CORS policies
- **Secret Management**: All secrets managed via environment variables
- **Dependency Scanning**: Regular security scans of dependencies

### Configuration Security
- Database connections use encrypted connections
- Redis authentication enabled
- Secure session management
- Configurable security headers

## Disclosure Policy

We follow responsible disclosure principles:

1. **Private Disclosure**: Vulnerabilities are reported privately first
2. **Coordinated Release**: We coordinate with reporters on disclosure timing
3. **Credit**: We credit security researchers who responsibly report vulnerabilities
4. **No Retaliation**: We do not pursue legal action against security researchers acting in good faith

## Security Updates

Security updates are released as:
- **Patch releases** for critical vulnerabilities
- **Minor releases** for high/medium severity issues
- **Major releases** for significant security improvements

## Contact Information

- **Security Email**: `security@ctiscraper.dev`
- **General Issues**: GitHub Issues
- **Documentation**: See README.md

## Acknowledgments

We appreciate the security research community's efforts in helping us maintain a secure codebase. Security researchers who responsibly disclose vulnerabilities will be acknowledged in our security advisories.