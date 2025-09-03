# Changelog

All notable changes to CTI Scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI/CD pipeline with security scanning
- Comprehensive security policy and contributing guidelines
- Enhanced .gitignore with security-focused patterns
- Environment variable configuration template
- Automated dependency vulnerability scanning

### Changed
- Updated all dependencies to latest secure versions
- Removed hardcoded credentials from configuration
- Improved code documentation and type hints
- Enhanced security practices and guidelines

### Security
- Fixed potential SQL injection vulnerabilities
- Updated cryptography library to latest version
- Removed debug prints and sensitive TODOs
- Implemented proper environment variable handling

## [2.0.0] - 2025-01-15

### Added
- **PostgreSQL Database**: Replaced SQLite with production-grade PostgreSQL
- **Async/Await Support**: Full async support with FastAPI and SQLAlchemy
- **Connection Pooling**: Efficient database connection management
- **Background Tasks**: Celery worker system for async operations
- **Redis Caching**: High-performance caching and message queuing
- **Docker Containerization**: Production-ready container orchestration
- **Nginx Reverse Proxy**: Professional-grade web server with rate limiting
- **Content Quality Assessment**: LLM-based quality scoring system
- **TTP Extraction Engine**: Advanced threat technique detection
- **Modern Web Interface**: HTMX-powered dynamic UI

### Changed
- **Architecture**: Complete rewrite with modern async architecture
- **Performance**: 10x improvement in concurrent operations
- **Scalability**: Horizontal scaling support
- **Security**: Enhanced security features and practices
- **Monitoring**: Built-in health checks and metrics

### Deprecated
- SQLite database support
- Old CLI interface
- Legacy web interface

### Removed
- Old architecture components
- Deprecated APIs and endpoints
- Legacy configuration formats

### Fixed
- Database locking issues
- Memory leaks in long-running processes
- Connection timeout problems
- Rate limiting inconsistencies

### Security
- Input validation for all endpoints
- SQL injection protection
- XSS protection
- Rate limiting implementation
- CORS configuration
- Environment variable configuration

## [1.2.3] - 2024-12-10

### Fixed
- SQL injection vulnerability in search functionality
- Memory leak in RSS parsing
- Connection timeout issues
- Rate limiting bypass

### Security
- Updated dependencies with security patches
- Enhanced input validation
- Improved error handling

## [1.2.2] - 2024-11-25

### Added
- Enhanced logging system
- Better error reporting
- Configuration validation

### Fixed
- RSS feed parsing issues
- Database connection problems
- Memory usage optimization

## [1.2.1] - 2024-11-15

### Added
- Content deduplication
- Source health monitoring
- Basic web interface

### Changed
- Improved RSS parsing accuracy
- Better error handling
- Enhanced logging

### Fixed
- Memory leaks in content processing
- Database connection issues
- File handling problems

## [1.2.0] - 2024-10-30

### Added
- RSS feed support
- Content extraction
- Basic database storage
- CLI interface

### Changed
- Improved content parsing
- Better source management
- Enhanced error handling

## [1.1.0] - 2024-09-15

### Added
- Basic web scraping functionality
- Source configuration
- Simple data storage

### Changed
- Improved performance
- Better error handling

## [1.0.0] - 2024-08-01

### Added
- Initial release
- Basic web scraping
- Simple data collection
- Basic CLI interface

---

## Migration Guides

### Upgrading from 1.x to 2.0

1. **Database Migration**: Export data from SQLite and import to PostgreSQL
2. **Configuration**: Update to new environment variable format
3. **Dependencies**: Install new requirements
4. **Docker**: Use new docker-compose configuration

### Upgrading from 1.1 to 1.2

1. **Database**: Backup existing data
2. **Configuration**: Update RSS feed configurations
3. **Dependencies**: Update to latest versions

---

## Release Notes

### Version 2.0.0
This is a major release with significant architectural improvements. The new async architecture provides better performance, scalability, and reliability. The addition of PostgreSQL, Redis, and Docker makes CTI Scraper production-ready.

### Version 1.2.3
Security-focused release addressing critical vulnerabilities and improving overall stability.

### Version 1.0.0
Initial release with basic functionality for web scraping and data collection.

---

## Support

For support and questions:
- **Issues**: GitHub issue tracker
- **Documentation**: Project README and docs
- **Security**: See SECURITY.md for security issues

---

**Note**: This changelog follows the Keep a Changelog format. All dates are in YYYY-MM-DD format.
