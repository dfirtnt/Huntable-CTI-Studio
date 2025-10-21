# CTI Scraper Process Diagrams

ASCII diagrams of the main workflows in the CTI Scraper system, designed to fit on single pages for PowerPoint slides.

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CTI Scraper Architecture                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Web Interface  │    │   Background    │    │   Database      │
│                 │    │                 │    │     Tasks       │    │                 │
│ • RSS Feeds     │───▶│ • FastAPI App   │    │ • Celery Worker │    │ • PostgreSQL    │
│ • Web Scraping  │    │ • Dashboard     │    │ • Scheduler     │    │ • Redis Cache   │
│ • 34 Sources    │    │ • Search/Filter │    │ • Collection    │    │ • pgvector      │
│ • Browser Ext.  │    │ • RAG Chat      │    │ • AI Analysis   │    │ • Async Manager │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        Docker Container Environment                            │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │    Web      │  │   Worker    │  │  Scheduler  │  │   Ollama    │          │
│  │  (FastAPI)  │  │  (Celery)   │  │  (Celery)   │  │    (LLM)    │          │
│  │   Port 8001 │  │             │  │             │  │  Port 11434 │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ PostgreSQL  │  │    Redis    │  │     CLI     │  │   Backup    │          │
│  │   Port 5432 │  │  Port 6379  │  │   Service   │  │   System    │          │
│  │  + pgvector │  │             │  │             │  │             │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 2. Article Collection Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Article Collection Workflow                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   Celery Beat   │
│   Scheduler     │
│   (Every 30min) │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ check_all_sources│
│     Task        │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Source List   │───▶│  RSS Parser     │───▶│ Modern Scraper  │
│   (34 sources)  │    │                 │    │                 │
└─────────────────┘    └─────────┬───────┘    └─────────┬───────┘
                                 │                      │
                                 ▼                      ▼
                        ┌─────────────────┐    ┌─────────────────┐
                        │  Feed Content   │    │  Web Content    │
                        │  Extraction     │    │  Extraction     │
                        └─────────┬───────┘    └─────────┬───────┘
                                  │                      │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Content Processor│
                                    │                 │
                                    │ • Deduplication │
                                    │ • Quality Filter│
                                    │ • Normalization │
                                    └─────────┬───────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │   Database      │
                                    │   Storage       │
                                    └─────────────────┘
```

## 3. Content Processing & Deduplication

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      Content Processing & Deduplication                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   Raw Articles  │
│   (from RSS/Web)│
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Content Processor│
│                 │
│ 1. Validation   │
│ 2. Normalization│
│ 3. Enhancement  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Duplicate      │    │  Content Hash   │    │  URL + Title    │
│  Detection      │    │  Check          │    │  Check          │
│                 │    │                 │    │                 │
│ • Content Hash  │───▶│ • SHA256 Hash   │───▶│ • Normalized    │
│ • URL Check     │    │ • Exact Match   │    │ • Combination   │
│ • Similarity    │    │ • Fast Lookup   │    │ • RSS Updates   │
└─────────┬───────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐
│ Quality Filter  │
│                 │
│ • Min Length    │
│ • Age Filter    │
│ • Source Rules  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Threat Hunting  │
│    Scoring      │
│                 │
│ • Perfect Disc. │
│ • Good Disc.    │
│ • LOLBAS        │
│ • Intelligence  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Unique Articles │
│   (Stored)      │
└─────────────────┘
```

## 4. Threat Hunting Scoring System

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Threat Hunting Scoring System                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│ Article Content │
│ (Title + Body)  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Keyword Matching│
│                 │
│ • Perfect Disc. │
│ • Good Disc.    │
│ • LOLBAS        │
│ • Intelligence  │
│ • Negative      │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Score Calculation│
│                 │
│ Perfect: 75pts  │
│ LOLBAS: 10pts   │
│ Intel: 10pts    │
│ Good: 5pts      │
│ Negative: -10pts│
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Final Score     │
│ (0-100 range)   │
└─────────────────┘

Keyword Categories:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Perfect Disc.   │    │ Good Disc.      │    │ LOLBAS Exec.    │
│                 │    │                 │    │                 │
│ • rundll32      │    │ • temp          │    │ • certutil      │
│ • powershell.exe│    │ • ==            │    │ • cmd           │
│ • EventID       │    │ • c:\windows\   │    │ • schtasks      │
│ • .lnk          │    │ • .bat          │    │ • wmic          │
│ • MZ            │    │ • .ps1          │    │ • bitsadmin     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 5. Web Interface Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Web Interface Workflow                             │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   User Browser  │
│                 │
│ • Articles Page │
│ • Sources Page  │
│ • Search/Filter │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   FastAPI App   │
│   (Port 8001)   │
│                 │
│ • Jinja2 Templates│
│ • Static Files  │
│ • API Endpoints │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Async Database  │
│    Manager      │
│                 │
│ • Connection Pool│
│ • Query Builder │
│ • Result Mapping│
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   PostgreSQL    │
│   Database      │
│                 │
│ • Articles Table│
│ • Sources Table │
│ • Annotations   │
└─────────────────┘

API Endpoints:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ /api/articles   │    │ /api/sources    │    │ /api/health     │
│                 │    │                 │    │                 │
│ • List Articles │    │ • List Sources  │    │ • Health Check  │
│ • Filter/Sort   │    │ • Add/Edit      │    │ • DB Status     │
│ • Pagination    │    │ • Health Status │    │ • Service Status│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 6. Background Task Processing

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Background Task Processing                             │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Celery Beat    │
│   Scheduler     │
│                 │
│ • Every 30min   │
│ • Daily 2AM     │
│ • Daily 6AM     │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   Task Queue    │
│    (Redis)      │
│                 │
│ • source_checks │
│ • priority_checks│
│ • maintenance   │
│ • reports       │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Celery Workers  │
│                 │
│ • check_all_sources│
│ • check_source  │
│ • cleanup_old_data│
│ • generate_daily_report│
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Task Execution  │
│                 │
│ • Source Health │
│ • Content Collection│
│ • Data Cleanup  │
│ • Report Gen    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   Database      │
│   Updates       │
│                 │
│ • Source Stats  │
│ • Article Count │
│ • Health Metrics│
└─────────────────┘
```

## 7. Database Schema

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Database Schema                                    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│    sources      │
│                 │
│ • id (PK)       │
│ • identifier    │
│ • name          │
│ • url           │
│ • rss_url       │
│ • tier          │
│ • active        │
│ • config (JSON) │
│ • last_check    │
└─────────┬───────┘
          │
          │ 1:N
          ▼
┌─────────────────┐
│    articles     │
│                 │
│ • id (PK)       │
│ • source_id (FK)│
│ • canonical_url │
│ • title         │
│ • content       │
│ • content_hash  │
│ • published_at  │
│ • metadata (JSON)│
│ • word_count    │
│ • hunt_score    │
└─────────┬───────┘
          │
          │ 1:N
          ▼
┌─────────────────┐
│article_annotations│
│                 │
│ • id (PK)       │
│ • article_id (FK)│
│ • annotation_type│
│ • selected_text │
│ • start_position│
│ • end_position  │
│ • embedding     │
│ • used_for_training│
└─────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  source_checks  │    │  content_hashes │    │chunk_classification│
│                 │    │                 │    │    _feedback     │
│ • id (PK)       │    │ • id (PK)       │    │                 │
│ • source_id (FK)│    │ • content_hash  │    │ • id (PK)       │
│ • check_time    │    │ • article_id    │    │ • article_id (FK)│
│ • success       │    │ • first_seen    │    │ • chunk_text    │
│ • articles_found│    └─────────────────┘    │ • model_classification│
└─────────────────┘                          │ • is_correct     │
                                             │ • used_for_training│
                                             └─────────────────┘
```

## 8. AI-Powered Analysis Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          AI-Powered Analysis Workflow                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│ Article Content │
│ (Title + Body)  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Content Filter  │
│                 │
│ • ML Pre-filter │
│ • Cost Reduction│
│ • Quality Check │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   LLM Services  │    │   RAG Chat      │    │ SIGMA Generation│
│                 │    │                 │    │                 │
│ • Ollama (Local)│    │ • Vector Search │    │ • AI Analysis   │
│ • OpenAI GPT-4  │    │ • Context Build │    │ • pySIGMA Valid │
│ • Claude 3      │    │ • Semantic Q&A  │    │ • Rule Creation │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Analysis Types  │    │ Vector Database │    │ Rule Validation │
│                 │    │                 │    │                 │
│ • Summaries     │    │ • Embeddings    │    │ • Syntax Check  │
│ • Classifications│   │ • Similarity   │    │ • Error Fix     │
│ • IOC Extraction│    │ • Context      │    │ • Retry Logic   │
│ • Custom Prompts│    │ • pgvector     │    │ • Audit Trail   │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────┬───────────┼──────────────────────┘
                     │           │
                     ▼           ▼
            ┌─────────────────┐    ┌─────────────────┐
            │   Database      │    │   User Interface│
            │   Storage       │    │                 │
            │                 │    │ • Chat Interface│
            │ • Metadata      │    │ • Rule Display  │
            │ • Results       │    │ • Analysis View │
            │ • Embeddings    │    │ • Export Options│
            └─────────────────┘    └─────────────────┘
```

## 9. ML Training Data Annotation System

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ML Training Data Annotation System                       │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│ Article Detail  │
│     Page        │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Text Selection  │
│                 │
│ • User Clicks   │
│ • Drag to Select│
│ • Auto-Expand   │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Length Validation│
│                 │
│ • Min: 950 chars│
│ • Max: 1050 chars│
│ • Auto 1000     │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Annotation Modal│
│                 │
│ • Huntable      │
│ • Not Huntable  │
│ • Confidence    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Database Storage│
│                 │
│ • article_annotations│
│ • Vector Embeddings│
│ • Training Flag │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Model Training  │
│                 │
│ • Batch Process │
│ • Retrain Model │
│ • Mark as Used  │
└─────────────────┘
```

## 10. Automated Backup System

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Automated Backup System                              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│ Cron Scheduler  │
│                 │
│ • Daily 2:00 AM │
│ • Weekly 3:00 AM│
│ • Requires Docker│
│ • Manual Setup  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Backup Script   │
│                 │
│ • backup_restore.sh│
│ • Full System   │
│ • Database Only │
│ • Files Only    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Database Backup │    │ Volume Backup   │    │ File Backup     │
│                 │    │                 │    │                 │
│ • PostgreSQL    │    │ • Docker Volumes│    │ • Config Files  │
│ • pg_dump       │    │ • Stop Containers│   │ • Models        │
│ • Compression   │    │ • Tar Archive   │    │ • Outputs       │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────┬───────────┼──────────────────────┘
                     │           │
                     ▼           ▼
            ┌─────────────────┐    ┌─────────────────┐
            │ Backup Archive  │    │ Retention Policy│
            │                 │    │                 │
            │ • Timestamped   │    │ • 7 Daily       │
            │ • Compressed    │    │ • 4 Weekly      │
            │ • Verified      │    │ • 3 Monthly     │
            │ • Checksums     │    │ • 50GB Max      │
            └─────────────────┘    └─────────────────┘

Note: Cron jobs are configured but require Docker to be running.
Manual backups via CLI: ./scripts/backup_restore.sh create
```

## 11. CLI Tool Service Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLI Tool Service Workflow                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   User Command  │
│                 │
│ • ./run_cli.sh  │
│ • init/collect  │
│ • backup/export │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Docker Container│
│                 │
│ • CLI Service   │
│ • Same Database │
│ • Shared Config │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Command Router   │    │ Database Access │    │ File Operations │
│                 │    │                 │    │                 │
│ • init          │    │ • PostgreSQL    │    │ • Config Files  │
│ • collect       │    │ • Async Manager │    │ • Export Data   │
│ • backup        │    │ • Same as Web   │    │ • Log Files     │
│ • rescore       │    │ • Consistency   │    │ • Model Files   │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Command Execution│    │ Data Operations │    │ Output Handling│
│                 │    │                 │    │                 │
│ • Source Mgmt   │    │ • CRUD Ops      │    │ • JSON/CSV     │
│ • Article Proc  │    │ • Queries       │    │ • Logs          │
│ • AI Analysis   │    │ • Transactions  │    │ • Status        │
│ • Embeddings    │    │ • Consistency   │    │ • Errors        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 12. Browser Extension Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Browser Extension Workflow                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   User Browser  │
│                 │
│ • Article Page  │
│ • Extension Icon│
│ • Click to Send │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Content Script  │
│                 │
│ • Extract Title │
│ • Extract Body  │
│ • Get URL       │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Extension Popup │
│                 │
│ • Review Content│
│ • Configure API │
│ • Force Scrape  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Background Script│
│                 │
│ • API Call      │
│ • Error Handling│
│ • Response      │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ CTIScraper API  │
│                 │
│ • /api/scrape-url│
│ • Process Article│
│ • Threat Scoring│
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Result Handling  │
│                 │
│ • Open Article  │
│ • Show Status   │
│ • Error Display │
└─────────────────┘
```

## 13. HTTP Client & Rate Limiting

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        HTTP Client & Rate Limiting                              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   HTTP Request  │
│                 │
│ • URL           │
│ • Headers       │
│ • Source ID     │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│  Robots Checker │
│                 │
│ • robots.txt    │
│ • Rate Limiting │
│ • User Agent    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│  Rate Limiter   │
│                 │
│ • Domain Delay  │
│ • Exponential   │
│ • Backoff       │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Conditional Cache│
│                 │
│ • ETag          │
│ • Last-Modified │
│ • 304 Handling  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│  HTTP Request   │
│                 │
│ • Browser Headers│
│ • SSL Handling  │
│ • Encoding      │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   Response      │
│                 │
│ • Content       │
│ • Headers       │
│ • Status Code   │
└─────────────────┘
```

## Usage Notes

These diagrams are designed to fit on single pages for easy screenshot capture into PowerPoint slides. Each diagram shows a specific workflow or component of the CTI Scraper system:

1. **System Architecture** - Overall system components and Docker environment with all services
2. **Article Collection** - How articles are collected from RSS feeds and web scraping
3. **Content Processing** - Deduplication, quality filtering, and scoring pipeline
4. **Threat Hunting Scoring** - Keyword-based scoring system for threat intelligence relevance
5. **Web Interface** - FastAPI application and database interaction
6. **Background Tasks** - Celery-based task scheduling and execution
7. **Database Schema** - PostgreSQL table relationships and structure with new tables
8. **AI-Powered Analysis** - LLM integration, RAG chat, and SIGMA rule generation workflows
9. **ML Training Data Annotation** - Annotation system with auto-expand functionality for ML training
10. **Automated Backup System** - Backup scheduling, retention policies, and verification
11. **CLI Tool Service** - Command-line interface workflow and database consistency
12. **Browser Extension** - Browser extension workflow for direct article ingestion
13. **HTTP Client** - Rate limiting, robots.txt compliance, and request handling

Each diagram uses consistent ASCII art styling and is optimized for readability when captured as screenshots.
