# CTI Scraper v4.0.0 "Kepler"

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docker.com)
[![CI/CD](https://github.com/starlord/CTIScraper/workflows/CI/badge.svg)](https://github.com/starlord/CTIScraper/actions)
[![Security](https://img.shields.io/badge/security-audited-green.svg)](.github/SECURITY.md)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

A comprehensive threat intelligence aggregation and analysis platform designed for security researchers and threat hunters.

## 🚀 Key Features
- Multi-source aggregation: Collect from curated RSS feeds, blogs, and vendor sites.
- AI-powered analysis: Scoring, IOC extraction, SIGMA rule generation, and similarity matching.
- Web interface + REST API with OpenAPI docs; backup management included.
- RAG-powered chat with semantic search across collected intelligence.
- SIGMA rule system: AI rule generation with similarity matching against community rules.
- OS Detection: Automated operating system detection for threat intelligence articles (Windows/Linux/MacOS).
- Agentic Workflow: LangGraph-based pipeline (Junk Filter → Ranking → OS Detection → Extraction → SIGMA → Similarity → Queue).
- Workflow executions observability: execution table exposes observable counts from ExtractAgent sub-agents.

## 🏗️ Architecture
- **Core Components**: FastAPI, PostgreSQL (with pgvector), Redis, Celery workers, LangGraph server, and Docker.
- **Data Flow**: Collection, processing, and analysis pipelines ensure efficiency.
- **Workflow Orchestration**: LangGraph-based state machine for automated threat intelligence processing.
- **Architecture**: See [Docker Architecture Guide](docs/deployment/DOCKER_ARCHITECTURE.md) for detailed component overview.

## 🚀 Getting Started
### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for development)

### Setup and Access
1. Clone the repository and navigate to the folder.
2. Run the setup script:
   ```bash
   git clone https://github.com/CTIScraper.git
   cd CTIScraper
   ./start.sh
   ```
3. Access the application:
   - **Web Interface**: [http://localhost:8001](http://localhost:8001)
   - **API Documentation**: [http://localhost:8001/docs](http://localhost:8001/docs)
   - **LangGraph Server**: [http://localhost:2024](http://localhost:2024) (workflow debugging)

## 📚 Documentation
- **[Getting Started Guide](docs/deployment/GETTING_STARTED.md)**: Quick deployment guide.
- **[API Reference](docs/API_ENDPOINTS.md)**: Comprehensive API documentation (133+ endpoints).
- **[Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)**: Container setup and services.
- **[SIGMA Detection Rules](docs/features/SIGMA_DETECTION_RULES.md)**: Rule generation and matching system.
- **[RAG System](docs/RAG_SYSTEM.md)**: Retrieval-Augmented Generation for threat intelligence.
- **[OS Detection](docs/features/OS_DETECTION.md)**: Automated operating system detection system.
- **[Agentic Workflow](docs/LANGGRAPH_INTEGRATION.md)**: LangGraph-based automated threat processing pipeline.

## 🤝 Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments
- OpenAI for GPT-4 API access.
- Anthropic for Claude API access.
- Docker for containerization.
