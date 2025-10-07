# Enhanced GPT-4o ranking endpoint with content filtering
from fastapi import HTTPException, Request
from datetime import datetime
import httpx
import os
import logging

# Import the app instance and other dependencies
from src.web.modern_main import app, async_db_manager, logger
from src.models.article import ArticleUpdate

@app.post("/api/articles/{article_id}/gpt4o-rank-optimized")
async def api_gpt4o_rank_optimized(article_id: int, request: Request):
    """Enhanced API endpoint for GPT4o SIGMA huntability ranking with content filtering."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')
        use_filtering = body.get('use_filtering', True)  # Enable filtering by default
        min_confidence = body.get('min_confidence', 0.7)  # Confidence threshold
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Import the optimizer
        from src.utils.gpt4o_optimizer import optimize_article_content, estimate_gpt4o_cost
        
        # Optimize content if filtering is enabled
        if use_filtering:
            logger.info(f"Optimizing content for article {article_id} with confidence threshold {min_confidence}")
            optimization_result = await optimize_article_content(
                article.content, 
                min_confidence=min_confidence,
                article_metadata=article.article_metadata,
                content_hash=article.content_hash
            )
            
            if optimization_result['success']:
                content_to_analyze = optimization_result['filtered_content']
                cost_savings = optimization_result['cost_savings']
                tokens_saved = optimization_result['tokens_saved']
                chunks_removed = optimization_result['chunks_removed']
                
                logger.info(f"Content optimization completed: "
                           f"{tokens_saved:,} tokens saved, "
                           f"${cost_savings:.4f} cost savings, "
                           f"{chunks_removed} chunks removed")
            else:
                logger.warning("Content optimization failed, using original content")
                content_to_analyze = article.content
                cost_savings = 0.0
                tokens_saved = 0
                chunks_removed = 0
        else:
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0
        
        # Truncate content if still too long (GPT4o has 128K token limit, roughly 500K characters)
        max_chars = 400000  # Leave room for prompt
        if len(content_to_analyze) > max_chars:
            content_to_analyze = content_to_analyze[:max_chars] + "\n\n[Content truncated due to length]"
        
        # SIGMA-focused prompt (same as original)
        sigma_prompt = """# Blog Content SIGMA-Suitability Huntability Ranking System

## Your Role

You are a detection engineer evaluating cybersecurity blog content specifically for its suitability to create SIGMA detection rules. Rate content based on how directly it maps to structured log data sources including Windows Event Logs, Sysmon, Linux auditd/Syslog, macOS system logs, AND cloud service logs (AWS CloudTrail, Azure Activity, GCP Audit).

## SIGMA-Focused Scoring (1-10 Scale)

Only content that maps to structured log telemetry receives points. Ignore network payloads, binary analysis, or packet-level details.

## Important Notes

- Do not award points for atomic IOCs (file hashes, IPs, or one-off domains).
- Filename/path patterns and directory conventions are acceptable if they indicate repeatable behavior.
- Only award points for observables that map directly to Windows Event Logs, Sysmon, Linux auditd/Syslog, or macOS system logs.

### Category A – Process Creation & Command-Line Arguments (0-4 pts)

**Data Sources:** 
- Windows: Sysmon Event ID 1, Security 4688
- Linux: process logs, auditd
- **macOS: Endpoint Security process events, unified logging (log show)**
- Cloud: CLI commands in CloudTrail/Activity logs

**Look For:**

- Parent → child process chains with full paths
- Exact command-line strings with arguments, switches, flags
- Process execution sequences
- Cloud CLI commands (aws, az, gcloud) with specific parameters
- **macOS-specific:** osascript commands, launchctl usage, security framework calls

**Scoring:**

- 0 = No process/command details
- 1 = Vague mentions ("runs PowerShell", "uses AWS CLI", or "executes AppleScript")
- 2 = Partial arguments or missing execution context
- 3 = Detailed examples but limited coverage
- 4 = Multiple detailed command chains with full arguments

### Category B – Persistence & System/Service Modification (0-3 pts)

**Data Sources:** 
- Windows: Sysmon Event IDs 12/13/19/7045, Security 4697
- Linux: auditd, systemd logs
- **macOS: LaunchAgent/LaunchDaemon creation, login items, authorization database changes**
- Cloud: AWS CloudTrail, Azure Activity

**Look For:**

- Registry keys with exact paths and values (Windows)
- Service creation/modification details
- Scheduled tasks, cron jobs, or **macOS LaunchAgents/LaunchDaemons**
- Cloud service configurations (IAM roles, SNS topics, Lambda functions, etc.)
- API calls that establish persistence or modify services
- **macOS persistence:** ~/Library/LaunchAgents, /Library/LaunchDaemons, login items, authorization plugins

**Scoring:**

- 0 = No persistence/modification details
- 1 = Generic mention ("creates persistence" or "modifies cloud config")
- 2 = Specific mechanism but incomplete details
- 3 = Exact configurations, API calls, plist files, or settings ready for SIGMA rules

### Category C – Log-Correlated Behavior (0-2 pts)

**Data Sources:** Multiple log sources in sequence (Windows/Linux/macOS/Cloud)

**Look For:**

- Cross-log correlations (process → network, cloud API → local execution)
- Event sequences that can be chained in SIGMA rules
- Time-based correlations between different log types
- Cloud service chains (EC2 → SNS → external endpoint)
- **macOS correlations:** Endpoint Security events + unified logging + authorization logs

**Scoring:**

- 0 = Single log source only
- 1 = Limited correlation opportunities
- 2 = Clear multi-log correlation patterns

### Category D – Structured Log Patterns (0-1 pt)

**Data Sources:** Any structured log format (file creation, API calls, service events)

**Look For:**

- File path patterns or naming conventions (not hashes)
- API call patterns with specific parameters
- Service usage patterns or anomalous configurations
- Structured event patterns in any log format
- **macOS-specific:** .plist file patterns, app bundle structures, Gatekeeper/XProtect logs

**Scoring:**

- 0 = No usable structured patterns
- 1 = Clear structured patterns present

## Important: Multi-Platform Content

**AWS CloudTrail, Azure Activity Logs, GCP Audit Logs, and macOS system logs ARE valid SIGMA data sources.** Do not dismiss cloud-focused or macOS content. API calls, service configurations, LaunchAgent creation, and command execution are all huntable through structured logs.

**macOS SIGMA Data Sources Include:**
- Endpoint Security Framework events
- Unified Logging System (log show commands)  
- Authorization database logs
- LaunchAgent/LaunchDaemon plist files
- Gatekeeper and XProtect logs

## Scoring Bands

- **1-2:** Mostly strategic content, minimal SIGMA applicability
- **3-4:** Limited SIGMA potential, too generic for reliable rules
- **5-6:** Moderate SIGMA candidates with some specificity
- **7-8:** Strong SIGMA potential, multiple rule-ready observables
- **9-10:** Excellent SIGMA content, rules can be drafted immediately

## Output Format

**SIGMA HUNTABILITY SCORE: [1-10]**

**CATEGORY BREAKDOWN:**

- **Process/Command-Line (0-4):** [Score] - [Brief reasoning, noting platform if applicable]
- **Persistence/System Mods (0-3):** [Score] - [Brief reasoning, noting platform-specific mechanisms]
- **Log Correlation (0-2):** [Score] - [Brief reasoning]
- **Structured Patterns (0-1):** [Score] - [Brief reasoning]

**SIGMA-READY OBSERVABLES:**
[List specific elements that can directly become SIGMA rules, noting target platform]

**REQUIRED LOG SOURCES:**
[Windows Event IDs, Sysmon events, Linux logs, macOS log sources, OR cloud service logs needed]

**RULE FEASIBILITY:**
[Assessment of how quickly detection rules could be created, noting any platform-specific considerations]

## Instructions

Analyze the provided blog content using this SIGMA-focused rubric. All major platforms (Windows, Linux, macOS) and cloud service logs are valid SIGMA data sources. Focus on structured log patterns regardless of platform. Ignore only unstructured data like network payloads or binary analysis.

Please analyze the following blog content:

**Title:** {title}
**Source:** {source}
**URL:** {url}

**Content:**
{content}"""
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze
        )
        
        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
        
        # Save the analysis to the article's metadata
        if article.metadata is None:
            article.metadata = {}
        
        article.metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat(),
            'model': 'gpt-4o',
            'optimization_enabled': use_filtering,
            'cost_savings': cost_savings,
            'tokens_saved': tokens_saved,
            'chunks_removed': chunks_removed,
            'min_confidence': min_confidence if use_filtering else None
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(metadata=article.metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat(),
            "optimization": {
                "enabled": use_filtering,
                "cost_savings": cost_savings,
                "tokens_saved": tokens_saved,
                "chunks_removed": chunks_removed,
                "min_confidence": min_confidence if use_filtering else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
