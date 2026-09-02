# Architecture

ASCII diagrams of the main workflows in Huntable CTI Studio. Use these to orient services, queues, and data flow when debugging or extending the stack.

## 1. System Architecture

See [Docker Architecture](../deployment/docker-architecture.md) for the authoritative service/port/volume list; this diagram is a conceptual overview only.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Huntable CTI Studio Architecture                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Web Interface  │    │   Background    │    │   Database      │
│                 │    │                 │    │     Tasks       │    │                 │
│ • RSS Feeds     │───▶│ • FastAPI App   │    │ • Celery Worker │    │ • PostgreSQL    │
│ • Web Scraping  │    │ • Dashboard     │    │ • Scheduler     │    │ • Redis Cache   │
│ • Sources       │    │ • Search/Filter │    │ • Collection    │    │ • pgvector      │
│ • Browser Ext.  │    │ • MCP Retrieval │    │ • AI Analysis   │    │ • Async Manager │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        Docker Container Environment                            │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │    Web      │  │   Worker    │  │  Workflow   │  │  Scheduler  │          │
│  │  (FastAPI)  │  │  (Celery)   │  │   Worker   │  │  (Celery)   │          │
│  │   Port 8001 │  │             │  │  (Celery)  │  │             │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ PostgreSQL  │  │    Redis    │  │     CLI     │  │ Maintenance │          │
│  │   Port 5432 │  │  Port 6379  │  │  (profile)  │  │  / Backup   │          │
│  │  + pgvector │  │             │  │             │  │             │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 2. Article Collection Workflow

See [Source Configuration](../guides/source-config.md) for how individual sources are configured (schedule, crawl policy, selectors).

```text
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
│   (sources)     │    │                 │    │                 │
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

```text
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

See [Threat Hunting Scoring](../architecture/scoring.md) for the full scoring mechanics (diagram 4 below covers the category weights, but that page is the source of truth).

## 4. Threat Hunting Scoring System

```text
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
│ Geometric Score │
│ per category    │
│                 │
│ score = max *   │
│  (1 - 0.5^n)    │
│ n = match count │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Category maxima │
│                 │
│ Perfect: 75pts  │
│ LOLBAS: 10pts   │
│ Intel: 10pts    │
│ Good: 5pts      │
│ Negative: -15pts│
│ (each capped,   │
│  never reached) │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Final Score     │
│ (0-99.9 range)  │
└─────────────────┘

Keyword Categories (examples; see config/keyword_registry.yaml for the full,
tier-tagged list -- entries carry the exact match string the scorer checks,
including the .exe suffix where applicable):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Perfect Disc.   │    │ Good Disc.      │    │ LOLBAS Exec.    │
│                 │    │                 │    │                 │
│ • rundll32.exe  │    │ • temp          │    │ • certutil.exe  │
│ • powershell.exe│    │ • ==            │    │ • cmd.exe       │
│ • Event ID      │    │ • c:\windows\   │    │ • schtasks.exe  │
│ • .lnk          │    │ • .bat          │    │ • wmic.exe      │
│ • MZ            │    │ • .ps1          │    │ • bitsadmin.exe │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 5. Web Interface Workflow

```text
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
│ /api/articles   │    │ /api/sources    │    │ /health         │
│                 │    │                 │    │                 │
│ • List Articles │    │ • List Sources  │    │ • Health Check  │
│ • Filter/Sort   │    │ • Add/Edit      │    │ • DB Status     │
│ • Pagination    │    │ • Health Status │    │ • Service Status│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 6. Background Task Processing

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Background Task Processing                             │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Celery Beat    │
│   Scheduler     │
│                 │
│ • Every 30min   │
│ • Daily jobs    │
│ • Weekly jobs   │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   Task Queue    │
│    (Redis)      │
│                 │
│ • default       │
│ • workflows     │
│ • source_checks │
│ • connectivity  │
│ • collection x2 │
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
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Task Execution  │
│                 │
│ • Source Health │
│ • Content Collection│
│ • Data Cleanup  │
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

```text
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
│ • check_frequency│
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
│ • article_metadata (JSON)│
│ • word_count    │
│ • threat_hunting_score (metadata)   │
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

┌─────────────────┐    ┌─────────────────┐
│  source_checks  │    │chunk_classification│
│                 │    │    _feedback     │
│ • id (PK)       │    │                 │
│ • source_id (FK)│    │ • id (PK)       │
│ • check_time    │    │ • article_id (FK)│
│ • success       │    │ • model_classification│
│ • articles_found│    │ • is_correct     │
└─────────────────┘    │ • used_for_training│
                        └─────────────────┘
```

See [Schemas](../reference/schemas.md) for the full column-level reference across all tables.

## 8. AI-Powered Analysis Workflow

See [Pipelines](../concepts/pipelines.md) for the full agentic extraction execution order, and [Content Filtering](../features/content-filtering.md) for the pre-filter stage.

```text
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
│   LLM Services  │    │   RAG Service   │    │ SIGMA Generation│
│                 │    │                 │    │                 │
│ • LM Studio     │    │ • Vector Search │    │ • AI Analysis   │
│ • OpenAI        │    │ • Context Build │    │ • pySigma Valid │
│ • Anthropic     │    │ • MCP Retrieval │    │ • Rule Creation │
│ • Codex (opt.)  │    │                 │    │                 │
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
            │                 │    │ • Search UI     │
            │ • Metadata      │    │ • Rule Display  │
            │ • Results       │    │ • Analysis View │
            │ • Embeddings    │    │ • Export Options│
            └─────────────────┘    └─────────────────┘
```

## 9. ML Training Data Annotation System

```text
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
│ • Auto-expand to 1000│
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

See [Backup and Restore](../guides/backup-and-restore.md) for the full operational guide.

```text
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
│ • File Archive  │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐                         ┌─────────────────┐
│ Database Backup │                         │ File Backup     │
│                 │                         │                 │
│ • PostgreSQL    │                         │ • Config Files  │
│ • pg_dump       │                         │ • Models        │
│ • Compression   │                         │ • Outputs       │
└─────────┬───────┘                         └─────────┬───────┘
          │                                         │
          └──────────────────┬──────────────────────┘
                             │
                             ▼
            ┌─────────────────┐    ┌─────────────────┐
            │ Backup Archive  │    │ Retention Policy│
            │                 │    │                 │
            │ • Timestamped   │    │ • 7 Daily       │
            │ • Compressed    │    │ • 4 Weekly      │
            │ • Verified      │    │ • 3 Monthly     │
            │ • Checksums     │    │ • 50GB Max      │
            └─────────────────┘    └─────────────────┘

Note: Cron jobs are configured but require Docker to be running.
Manual system backups run through the authenticated maintenance service or host scripts.
```

## 11. CLI Tool Service Workflow

See [CLI Reference](../reference/cli.md) for the full command list.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLI Tool Service Workflow                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   User Command  │
│                 │
│ • ./run_cli.sh  │
│ • init/collect  │
│ • export/search │
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
│ • search        │    │ • Same as Web   │    │ • Log Files     │
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

See [Browser Extension](../guides/browser-extension.md) for install and usage instructions.

```text
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
│ Huntable CTI Studio API  │
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

```text
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

_Last updated: 2026-08-13_
_Last reviewed: 2026-09-01_
