# CTI Scraper v2.0.0 "Tycho"

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docker.com)
[![CI/CD](https://github.com/starlord/CTIScraper/workflows/CI/badge.svg)](https://github.com/starlord/CTIScraper/actions)
[![Security](https://img.shields.io/badge/security-audited-green.svg)](.github/SECURITY.md)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

A comprehensive threat intelligence aggregation and analysis platform designed for security researchers and threat hunters. CTI Scraper automates the collection, processing, and analysis of threat intelligence from multiple sources, providing actionable insights for cybersecurity professionals.

## 🎯 Key Features

### 🔍 Intelligent Threat Intelligence Collection
- **Multi-Source Aggregation**: Automated collection from 30+ RSS feeds, security blogs, and vendor sites
- **Smart Content Processing**: RSS-first collection with basic web scraping fallback and HTML cleaning
- **Duplicate Detection**: Intelligent deduplication using content hashing and similarity analysis
- **Source Health Monitoring**: Real-time monitoring with automatic failure detection and recovery

### 🤖 AI-Powered Analysis
- **Threat Hunting Scoring**: Rule-based relevance scoring using logarithmic formulas
- **Multi-Provider LLM Integration**: Support for OpenAI GPT-4o, Anthropic Claude, LMStudio (local), and Ollama (local)
- **IOC Extraction**: Hybrid IOC extraction combining iocextract with optional LLM validation
- **SIGMA Rule Generation**: AI-powered generation of detection rules with pySIGMA validation
- **RAG Chat Interface**: Conversational AI with threat intelligence database using semantic search
- **Vector Embeddings**: Sentence Transformers (all-mpnet-base-v2) for 768-dimensional semantic similarity
- **ML-Powered Content Filtering**: Machine learning model for automated chunk classification
- **Interactive Feedback System**: User feedback collection for continuous ML model improvement
- **Model Versioning & Comparison**: Track model performance changes and confidence improvements
- **Conversational Context**: Multi-turn conversation support with context memory

### 📊 Advanced Analytics
- **Text Annotation System**: Web-based interface for marking huntable vs non-huntable content
- **Keyword Classification**: Multi-tier keyword matching (perfect, good, LOLBAS, intelligence indicators)
- **Content Filtering**: Automated junk detection and quality assessment
- **Interactive Dashboards**: Real-time analytics for source health and content metrics

### 🌐 Modern Web Interface
- **Responsive Design**: Modern UI built with FastAPI and contemporary JavaScript
- **Real-time Updates**: Live monitoring of collection and processing status
- **Export Capabilities**: CSV export for annotations and classifications
- **RESTful API**: Comprehensive API for integration with other security tools
- **Automated Backup System**: Backup with database, config, and data protection
- **Backup Management**: Web-based backup creation, listing, and status monitoring
- **Database Management**: Command-line backup and restore tools for data protection
- **RAG Chat Interface**: Conversational AI with threat intelligence database using semantic search
- **Multi-Provider LLM**: OpenAI GPT-4o, Anthropic Claude, LMStudio, and Ollama integration with auto-fallback
- **Conversational Context**: Multi-turn conversations with context memory and follow-up questions
- **Clickable Results**: Direct links to article details from chat responses
- **ML Feedback Interface**: Interactive feedback system for model improvement with confidence tracking
- **Model Performance Analytics**: Visual comparison of model versions and confidence improvements

## 🏗️ Architecture

### Core Components
- **FastAPI Backend**: High-performance async web framework with automatic API documentation
- **PostgreSQL Database**: Robust data storage with advanced indexing and query optimization
- **pgvector Extension**: Vector similarity search for 768-dimensional semantic embeddings
- **Redis Cache**: High-speed caching and task queue management
- **Celery Workers**: Distributed task processing for scalable content collection
- **Sentence Transformers**: all-mpnet-base-v2 model for semantic embeddings and RAG functionality
- **Multi-Provider LLM Service**: OpenAI GPT-4o, Anthropic Claude, and Ollama with auto-fallback
- **RAG Generation Service**: LLM-powered response synthesis with conversation context
- **Docker Containers**: Containerized deployment for consistent environments

### Data Flow
1. **Collection**: RSS feed parsing (primary) with basic web scraping fallback
2. **Processing**: Content extraction, cleaning, and deduplication
3. **Analysis**: Rule-based scoring and AI-powered classification
4. **Embedding**: Vector generation using Sentence Transformers for semantic search
5. **Storage**: Structured data storage with full-text search and vector similarity capabilities
6. **RAG Generation**: LLM-powered synthesis of retrieved content with conversation context
7. **Presentation**: Real-time web interface, conversational AI, and API endpoints

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for development)

### ⚡ One-Command Setup
```bash
git clone https://github.com/starlord/CTIScraper.git
cd CTIScraper
./start.sh
```

### Access the Application
- **Web Interface**: http://localhost:8001
- **API Documentation**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health

### First Steps
1. Add your first source via the Sources page
2. Trigger content collection to test the system
3. View collected articles on the Articles page

**For detailed documentation, see [DOCUMENTATION.md](DOCUMENTATION.md)**

## 📚 Documentation

**For comprehensive documentation, see [DOCUMENTATION.md](DOCUMENTATION.md)**

### Quick Links
- **[API Reference](docs/API_ENDPOINTS.md)**: Complete API documentation
- **[Testing Guide](tests/TESTING.md)**: Comprehensive testing documentation
- **[Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)**: Container setup and architecture
- **[Backup System](docs/DATABASE_BACKUP_RESTORE.md)**: Backup and restore procedures

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and code standards.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI** for GPT-4o API access
- **Anthropic** for Claude API access
- **Ollama** for local LLM capabilities
- **Sentence Transformers** for semantic embeddings
- **FastAPI** for the web framework
- **PostgreSQL** for robust data storage
- **Redis** for caching and task queues
- **Docker** for containerization

