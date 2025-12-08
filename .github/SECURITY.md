# Security Policy

## Supported Versions

We actively maintain and provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability, please follow these steps:

### 1. **DO NOT** create a public GitHub issue

Security vulnerabilities should be reported privately to protect users until a fix is available.

### 2. Email Security Team

Send an email to: **security@ctiscraper.dev**

Include the following information:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Any suggested fixes or mitigations

### 3. Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Fix Development**: Within 30 days (for critical issues)
- **Public Disclosure**: After fix is released and deployed

### 4. What to Expect

- We will acknowledge receipt of your report
- We will keep you updated on our progress
- We will work with you to understand and resolve the issue
- We will credit you in our security advisories (unless you prefer to remain anonymous)

## Security Measures

### Dependency Management
- All dependencies are pinned to specific versions
- Regular security audits using `pip-audit` and `safety`
- Automated dependency updates in CI/CD pipeline

### Code Security
- Static code analysis with `flake8` and `mypy`
- Security-focused code reviews
- Automated security scanning in CI/CD

### Infrastructure Security
- Docker containers run with non-root users
- Minimal base images (Alpine Linux)
- Regular security updates for base images
- Network isolation between services

### Data Protection
- Environment variables for sensitive configuration
- No hardcoded credentials in source code
- Database connections use SSL/TLS
- Regular security backups

## Security Best Practices

### For Users
1. **Keep Dependencies Updated**: Regularly update your dependencies
2. **Use Environment Variables**: Never hardcode API keys or passwords
3. **Network Security**: Use HTTPS in production environments
4. **Access Control**: Implement proper authentication and authorization
5. **Monitoring**: Set up logging and monitoring for security events

### For Developers
1. **Code Reviews**: All code changes require security review
2. **Testing**: Include security tests in your test suite
3. **Dependencies**: Audit dependencies before adding them
4. **Secrets**: Never commit secrets to version control
5. **Documentation**: Document security considerations

## Security Tools

We use the following tools to maintain security:

- **pip-audit**: Python package vulnerability scanning
- **safety**: Additional Python security checks
- **Trivy**: Container vulnerability scanning
- **GitHub Security Advisories**: Vulnerability tracking
- **Dependabot**: Automated dependency updates

## Security Updates

Security updates are released as soon as possible after a vulnerability is discovered and fixed. We follow semantic versioning:

- **Patch releases** (1.0.x): Security fixes and bug fixes
- **Minor releases** (1.x.0): New features and improvements
- **Major releases** (x.0.0): Breaking changes

## Contact

For security-related questions or concerns:
- Email: security@ctiscraper.dev
- GitHub: Create a private security advisory
- Documentation: See our security documentation in `/docs/security/`

## Acknowledgments

We thank the security researchers and community members who help us maintain the security of CTI Scraper. Your contributions are invaluable in keeping our users safe.

## License

This security policy is part of the CTI Scraper project and is subject to the same MIT License as the main project.