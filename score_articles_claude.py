#!/usr/bin/env python3
"""Score multiple articles using Claude 3.5 Sonnet with integer-only output."""

import httpx
import asyncio
import sys
import os
import subprocess
from email.utils import parsedate_to_datetime
from datetime import datetime

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print("Error: ANTHROPIC_API_KEY environment variable not set")
    sys.exit(1)

# Read the prompt template
with open("src/prompts/gpt4o_sigma_ranking.txt", "r") as f:
    prompt_template = f.read()

# Modify prompt: add instruction before URL
instruction = "\nDo not explain, justify, or include any text besides the score.\n\nOutput format:\n\n[integer only]\n\n"
prompt_template = prompt_template.replace("**URL:** {url}", instruction + "**URL:** {url}")

async def score_article(article_id, title, source, url, content, max_retries=3):
    """Score a single article using Claude 3.5 Sonnet."""
    full_prompt = prompt_template.format(
        title=title,
        source=source,
        url=url,
        content=content
    )
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": API_KEY,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 2000,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ]
                },
                timeout=120.0
            )
            
            if response.status_code == 429:
                # Rate limited - parse retry-after header and use exponential backoff
                retry_after_header = response.headers.get("retry-after")
                
                # Parse retry-after (seconds or HTTP date)
                retry_after = 30.0  # default
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header.strip())
                    except ValueError:
                        try:
                            retry_date = parsedate_to_datetime(retry_after_header)
                            now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                            delta = retry_date - now
                            retry_after = max(0.0, delta.total_seconds())
                        except (ValueError, TypeError):
                            retry_after = 30.0
                
                # Exponential backoff: max(retry_after, base_delay * 2^attempt)
                base_delay = 1.0
                max_delay = 60.0
                delay = max(retry_after, base_delay * (2 ** attempt))
                delay = min(delay, max_delay)
                
                if attempt < max_retries - 1:
                    print(f"Article {article_id}: Rate limited (429). Waiting {delay:.1f}s (retry-after: {retry_after:.1f}s) before retry {attempt+1}/{max_retries}...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"Article {article_id}: Rate limit exceeded after {max_retries} attempts")
                    return None
            
            if response.status_code != 200:
                print(f"Article {article_id}: Error {response.status_code}")
                print(response.text)
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return None
        
        result = response.json()
        usage = result.get('usage', {})
        score = result['content'][0]['text'].strip()
        
        return {
            'article_id': article_id,
            'score': score,
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0)
        }

async def main():
    """Main function to score all articles."""
    article_ids = [1909, 1866, 1860, 1937, 1794]
    
    # Fetch article data from database
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-F", "|", "-c", 
         f"SELECT a.id, a.title, a.canonical_url, s.name, a.content FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id IN ({','.join(map(str, article_ids))}) ORDER BY id;"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Database query failed: {result.stderr}")
        return
    
    articles = []
    for line in result.stdout.strip().split('\n'):
        if not line or '|' not in line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            articles.append({
                'id': int(parts[0]),
                'title': parts[1],
                'url': parts[2],
                'source': parts[3],
                'content': parts[4]
            })
    
    print(f"Scoring {len(articles)} articles with Claude 3.5 Sonnet...\n")
    
    # Score all articles concurrently
    tasks = [score_article(
        article_id=article['id'],
        title=article['title'],
        source=article['source'],
        url=article['url'],
        content=article['content']
    ) for article in articles]
    results = await asyncio.gather(*tasks)
    
    # Print results
    print("\nResults:")
    print("-" * 60)
    total_cost = 0
    for result in results:
        if result:
            # Anthropic pricing (as of 2024): $3/1M input, $15/1M output
            cost = (result['input_tokens'] / 1_000_000 * 3.00) + (result['output_tokens'] / 1_000_000 * 15.00)
            total_cost += cost
            print(f"Article {result['article_id']}: Score = {result['score']}")
            print(f"  Tokens: {result['input_tokens'] + result['output_tokens']} (in: {result['input_tokens']}, out: {result['output_tokens']})")
            print(f"  Cost: ${cost:.6f}")
            print()
    
    print("-" * 60)
    print(f"Total cost: ${total_cost:.6f} (${total_cost * 100:.2f} cents)")
    print(f"Average cost per article: ${total_cost / len([r for r in results if r]):.6f}")

if __name__ == "__main__":
    asyncio.run(main())

