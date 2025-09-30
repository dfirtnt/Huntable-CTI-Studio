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
│ • 40+ Sources   │    │ • Search/Filter │    │ • Collection    │    │ • Async Manager │
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
│  ┌─────────────┐  ┌─────────────┐                                              │
│  │ PostgreSQL  │  │    Redis    │                                              │
│  │   Port 5432 │  │  Port 6379  │                                              │
│  └─────────────┘  └─────────────┘                                              │
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
│   (40+ sources) │    │                 │    │                 │
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
└─────────────────┘

┌─────────────────┐    ┌─────────────────┐
│  source_checks  │    │  content_hashes │
│                 │    │                 │
│ • id (PK)       │    │ • id (PK)       │
│ • source_id (FK)│    │ • content_hash  │
│ • check_time    │    │ • article_id    │
│ • success       │    │ • first_seen    │
│ • articles_found│    └─────────────────┘
└─────────────────┘
```

## 8. HTTP Client & Rate Limiting

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

1. **System Architecture** - Overall system components and Docker environment
2. **Article Collection** - How articles are collected from RSS feeds and web scraping
3. **Content Processing** - Deduplication, quality filtering, and scoring pipeline
4. **Threat Hunting Scoring** - Keyword-based scoring system for threat intelligence relevance
5. **Web Interface** - FastAPI application and database interaction
6. **Background Tasks** - Celery-based task scheduling and execution
7. **Database Schema** - PostgreSQL table relationships and structure
8. **HTTP Client** - Rate limiting, robots.txt compliance, and request handling

Each diagram uses consistent ASCII art styling and is optimized for readability when captured as screenshots.
