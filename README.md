# 🔍 Security Article Pipeline

A focused tool for collecting, processing, and classifying security articles from RSS feeds and web sources. Designed to prepare high-quality training data for threat intelligence models.

## 🎯 Purpose

This pipeline helps security researchers and threat hunters:
- **Collect** articles from trusted security sources
- **Process** and clean content for analysis
- **Classify** articles for relevance and quality
- **Prepare** training data for ML model fine-tuning

## ✨ Features

### Core Functionality
- **RSS Feed Scraping**: Collect articles from security blogs and news sources
- **Web Scraping**: Extract content from individual articles
- **Content Processing**: Clean, deduplicate, and normalize text
- **Classification Pipeline**: Identify relevant articles for threat hunting
- **Data Export**: Export processed data in various formats

### Classification System
- **Relevance Scoring**: Identify articles useful for threat hunters
- **Quality Assessment**: Filter out low-quality or irrelevant content
- **Content Chunking**: Break articles into manageable pieces
- **Labeling Support**: Prepare data for supervised learning

## 🏗️ Architecture

```
src/
├── scraper/          # RSS and web scraping
├── processor/        # Content processing and cleaning
├── classifier/       # Classification and scoring
└── utils/           # Shared utilities

config/
├── sources.yaml     # RSS feed configurations
└── models.yaml      # Model configurations

data/
├── raw/            # Raw scraped articles
├── processed/      # Cleaned articles
└── labeled/        # Training data
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL (optional, for persistent storage)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/security-article-pipeline.git
   cd security-article-pipeline
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure sources**
   ```bash
   cp config/sources.yaml.example config/sources.yaml
   # Edit sources.yaml with your preferred RSS feeds
   ```

### Basic Usage

1. **Scrape articles**
   ```bash
   python -m src.scraper.main --sources config/sources.yaml
   ```

2. **Process content**
   ```bash
   python -m src.processor.main --input data/raw --output data/processed
   ```

3. **Classify articles**
   ```bash
   python -m src.classifier.main --input data/processed --output data/labeled
   ```

## 📊 Data Flow

1. **Collection**: RSS feeds → Raw articles
2. **Processing**: Raw articles → Cleaned content
3. **Classification**: Cleaned content → Scored articles
4. **Export**: Scored articles → Training datasets

## 🔧 Configuration

### Sources Configuration (`config/sources.yaml`)
```yaml
sources:
  - name: "The Hacker News"
    url: "https://thehackernews.com/"
    rss_url: "https://feeds.feedburner.com/TheHackersNews"
    tier: 1
    weight: 1.0
```

### Model Configuration (`config/models.yaml`)
```yaml
classification:
  relevance_threshold: 0.7
  quality_threshold: 0.6
  chunk_size: 512
  overlap: 50
```

## 📈 Output Formats

### Processed Articles
```json
{
  "id": "unique_id",
  "title": "Article Title",
  "content": "Cleaned article content...",
  "url": "https://example.com/article",
  "published_at": "2024-01-01T00:00:00Z",
  "source": "source_name",
  "relevance_score": 0.85,
  "quality_score": 0.78
}
```

### Training Data
```json
{
  "text": "Article chunk content...",
  "label": "relevant",
  "confidence": 0.92,
  "metadata": {
    "article_id": "unique_id",
    "chunk_index": 0,
    "source": "source_name"
  }
}
```

## 🧪 Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black src/
isort src/
flake8 src/
```

### Adding New Sources
1. Add RSS feed to `config/sources.yaml`
2. Test with `python -m src.scraper.main --test-source source_name`
3. Run full pipeline to verify

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🤝 Support

- **Issues**: Report bugs and feature requests on GitHub
- **Discussions**: Join the community discussions
- **Documentation**: See the [docs/](docs/) folder for detailed guides

---

**Note**: This tool is designed for research and educational purposes. Always respect website terms of service and robots.txt files when scraping content.
