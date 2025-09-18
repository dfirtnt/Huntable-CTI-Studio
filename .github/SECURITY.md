# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in CTI Scraper, please report it responsibly.

### How to Report

1. **Do NOT** create a public GitHub issue for security vulnerabilities
2. Send an email to [security@your-domain.com] with:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact assessment
   - Any suggested fixes or mitigations

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Initial Assessment**: We will provide an initial assessment within 5 business days
- **Resolution Timeline**: Critical vulnerabilities will be addressed within 30 days
- **Disclosure**: We follow coordinated disclosure practices

### Security Best Practices

When deploying CTI Scraper:

#### Environment Security
- [ ] Use strong, unique passwords for all database connections
- [ ] Enable TLS/SSL for all network connections
- [ ] Regularly rotate API keys and secrets
- [ ] Use environment variables for all sensitive configuration
- [ ] Enable firewall rules to restrict network access

#### Application Security
- [ ] Deploy behind a reverse proxy (nginx)
- [ ] Enable rate limiting on public endpoints
- [ ] Regular security updates for all dependencies
- [ ] Monitor application logs for suspicious activity
- [ ] Implement proper backup and recovery procedures

#### Data Protection
- [ ] Encrypt data at rest and in transit
- [ ] Implement proper access controls
- [ ] Regular security audits of collected data
- [ ] Compliance with applicable data protection regulations
- [ ] Secure deletion of sensitive data when no longer needed

### Known Security Considerations

#### LLM Integration
- API keys for external LLM services should be properly secured
- Content sent to external services may be logged by providers
- Consider using local LLM models (Ollama) for sensitive data

#### Web Interface
- The annotation interface allows arbitrary text selection and classification
- Admin access should be properly secured and monitored
- Regular session management and timeout policies should be enforced

#### Database Security
- PostgreSQL connections should use encrypted connections
- Regular database security patches should be applied
- Backup files should be encrypted and stored securely

### Security Updates

We will notify users of security updates through:
- GitHub Security Advisories
- Release notes with security patches
- Direct notification for critical vulnerabilities

### Bug Bounty

We currently do not offer a formal bug bounty program, but we recognize and appreciate security researchers who responsibly disclose vulnerabilities.

### Compliance

CTI Scraper is designed to support:
- SOC 2 compliance requirements
- GDPR data protection standards
- Industry-standard security frameworks
- Audit logging and monitoring requirements

For compliance-specific questions, please contact our security team.

---

**Last Updated**: January 2025
**Next Review**: July 2025