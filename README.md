# CTI Scraper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docker.com)

A comprehensive threat intelligence aggregation and analysis platform designed for security researchers and threat hunters.

## 🎯 Features

### Threat Intelligence Collection
- **Multi-Source Aggregation**: Automated collection from RSS feeds, blogs, and security vendor sites
- **Smart Content Processing**: Advanced text extraction and cleaning with readability scoring
- **Duplicate Detection**: Intelligent deduplication using content hashing and similarity analysis
- **Source Health Monitoring**: Automatic source validation and failure tracking

### Advanced Analysis
- **Threat Hunting Scoring**: ML-powered relevance scoring using keyword density and classification models
- **Text Annotation System**: Web-based interface for marking huntable vs non-huntable content
- **Keyword Classification**: Multi-tier keyword matching (perfect, good, LOLBAS, intelligence indicators)
- **Content Filtering**: Automated junk detection and quality assessment

### AI-Powered Features
- **LLM Integration**: Support for Ollama (local) and OpenAI models
- **Intelligent Classification**: GPT-4 powered article relevance assessment
- **Natural Language Queries**: Database chat interface for threat intelligence exploration
- **IOC Extraction**: Automated indicator of compromise detection

### Web Interface
- **Modern UI**: Responsive web interface built with FastAPI and modern JavaScript
- **Real-time Updates**: Live monitoring of collection and processing status
- **Interactive Analytics**: Visual dashboards for source health and content metrics
- **Export Capabilities**: CSV export for annotations and classified content

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.8+ (for development)
- PostgreSQL and Redis (handled by Docker)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/CTIScraper.git
   cd CTIScraper
   ```

2. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your configuration
   ```

3. **Start with Docker**
   ```bash
   docker-compose up -d
   ```

4. **Access the web interface**
   - Main interface: http://localhost:8000
   - Health checks: http://localhost:8000/health-checks

## 📋 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
POSTGRES_USER=cti_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=cti_scraper

# Redis
REDIS_PASSWORD=your_redis_password

# LLM Configuration (Optional)
CHATGPT_API_KEY=your_openai_api_key_here
OLLAMA_HOST=http://ollama:11434

# Application
LOG_LEVEL=INFO
WORKERS=4
```

### Source Configuration

Sources are configured in `config/sources.yaml`:

```yaml
sources:
  - name: "Example Security Blog"
    url: "https://example.com/feed.xml"
    type: "rss"
    tier: 1
    check_frequency: 900  # 15 minutes
```

## 🏗️ Architecture

### Components
- **Web Server**: FastAPI application with modern web interface
- **Worker Processes**: Celery workers for background scraping and processing
- **Scheduler**: Automated source checking and maintenance tasks
- **Database**: PostgreSQL for structured data storage
- **Cache**: Redis for session management and task queuing
- **Reverse Proxy**: Nginx for production deployments

### Classification System

**Article Classification** (Whole Article Level):
- `chosen`: Relevant threat intelligence
- `rejected`: Not relevant
- `unclassified`: Needs review

**Annotation Classification** (Text Chunk Level):
- `huntable`: Actionable threat intelligence
- `not_huntable`: Informational content

## 🔧 Development

### Local Development Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start development server**
   ```bash
   uvicorn src.web.modern_main:app --reload --host 0.0.0.0 --port 8000
   ```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Test specific components
pytest tests/test_scraping.py
```

## 📊 Usage Examples

### Adding Sources
1. Navigate to Sources page in web interface
2. Click "Add Source"
3. Configure RSS URL, check frequency, and tier
4. Save and monitor collection status

### Annotation Workflow
1. Browse to Articles page
2. Select an unclassified article
3. Mark article as "chosen" or "rejected"
4. For chosen articles, select text and annotate as "huntable" or "not huntable"
5. Export annotations for threat hunting use

### Database Queries
Use the AI Chat interface for natural language queries:
- "Show me all articles about PowerShell from the last week"
- "Find huntable content related to persistence techniques"
- "What sources have been most active recently?"

## 📈 Monitoring

### Health Checks
- **Application Health**: `/health-checks`
- **Database Connectivity**: Automatic monitoring
- **Source Status**: Real-time failure tracking
- **Worker Health**: Celery task monitoring

### Metrics
- Article collection rates
- Processing success/failure rates
- Classification accuracy
- Source availability

## 🔒 Security

### Best Practices
- All secrets managed via environment variables
- Database connections use encrypted connections
- Rate limiting on API endpoints
- Input validation and sanitization
- Regular dependency updates

### Data Privacy
- No external data transmission without explicit configuration
- Local LLM support via Ollama
- Configurable data retention policies

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add tests for new features
- Update documentation
- Use type hints where possible

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with FastAPI, SQLAlchemy, and modern web technologies
- Inspired by the threat intelligence community's need for better aggregation tools
- Special thanks to the open-source security tool ecosystem

## 📚 Documentation

- [Development Workflow](DEVELOPMENT_WORKFLOW.md)
- [AWS Deployment Guide](AWS_DEPLOYMENT_README.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## 💬 Support

- Create an issue for bug reports or feature requests
- Check existing documentation for common questions
- Review health checks for system status

---

**Note**: This tool is designed for legitimate security research and threat intelligence purposes. Users are responsible for compliance with applicable laws and regulations.