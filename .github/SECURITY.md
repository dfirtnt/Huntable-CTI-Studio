# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability within SousChef, please report it to us as described below.

### How to Report

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **Email**: Send details to security@souschef.dev (if this email exists)
2. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature
3. **Direct Contact**: Contact the maintainers directly through GitHub

### What to Include

When reporting a vulnerability, please include:

- **Description**: A clear description of the vulnerability
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Impact**: Potential impact and severity assessment
- **Affected Versions**: Which versions are affected
- **Suggested Fix**: If you have suggestions for fixing the issue

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Depends on severity and complexity

### Security Considerations

#### API Keys and Credentials

- **Never commit API keys** or credentials to the repository
- Use environment variables for all sensitive configuration
- Follow the `.env.example` template for configuration

#### Dependencies

- We regularly audit dependencies for known vulnerabilities
- Critical vulnerabilities are addressed immediately
- Moderate vulnerabilities are addressed in regular update cycles

#### Data Handling

- SousChef processes data locally when possible
- OpenAI API calls are made only for recipe generation
- No sensitive data is stored or logged unnecessarily

### Security Best Practices

#### For Users

1. **Environment Variables**: Always use environment variables for API keys
2. **Regular Updates**: Keep dependencies updated
3. **Input Validation**: Validate all inputs before processing
4. **Network Security**: Use HTTPS in production environments

#### For Developers

1. **Code Review**: All code changes require review
2. **Dependency Scanning**: Regular security audits
3. **Input Sanitization**: Sanitize all user inputs
4. **Error Handling**: Avoid exposing sensitive information in errors

### Known Security Considerations

#### OpenAI API Usage

- API keys are required for LLM features
- Keys should be kept secure and not shared
- Consider using API key rotation in production

#### CyberChef Operations

- Some operations may be computationally expensive
- Large inputs may cause memory issues
- Certain cryptographic operations may have side effects

### Security Updates

Security updates are released as:

- **Critical**: Immediate patch release
- **High**: Within 7 days
- **Medium**: Next regular release cycle
- **Low**: Next major release

### Contact Information

For security-related questions or concerns:

- **Primary**: GitHub Security Advisory
- **Secondary**: Direct contact with maintainers
- **Emergency**: Create a private issue with security label

---

**Thank you for helping keep SousChef and our users safe!**