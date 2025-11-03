#!/usr/bin/env python3
"""Score multiple articles using GPT-4o with integer-only output."""

import httpx
import asyncio
import sys
import os

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)

# Read the prompt template
with open("src/prompts/gpt4o_sigma_ranking.txt", "r") as f:
    prompt_template = f.read()

# Modify prompt: add instruction before URL
instruction = "\nDo not explain, justify, or include any text besides the score.\n\nOutput format:\n\n[integer only]\n\n"
prompt_template = prompt_template.replace("**URL:** {url}", instruction + "**URL:** {url}")

async def score_article(article_id, title, source, url, content, max_retries=3):
    """Score a single article using GPT-4o."""
    full_prompt = prompt_template.format(
        title=title,
        source=source,
        url=url,
        content=content
    )
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
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
                "temperature": 0.2
            },
                timeout=120.0
            )
            
            if response.status_code == 429:
                # Rate limited - wait and retry
                import json
                try:
                    error_data = response.json()
                    retry_after = float(error_data.get('error', {}).get('message', '').split('in ')[1].split('s')[0]) if 'in ' in error_data.get('error', {}).get('message', '') else 20.0
                    retry_after = max(retry_after, 20.0)  # At least 20 seconds
                except:
                    retry_after = 30.0
                
                if attempt < max_retries - 1:
                    print(f"Article {article_id}: Rate limited, waiting {retry_after:.1f}s before retry {attempt+1}/{max_retries}...")
                    await asyncio.sleep(retry_after)
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
        score = result['choices'][0]['message']['content'].strip()
        
        return {
            'article_id': article_id,
            'score': score,
            'input_tokens': usage.get('prompt_tokens', 0),
            'output_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0)
        }

async def main():
    """Main function to score all articles."""
    article_ids = [1909, 1866, 1860, 1937, 1794]
    
    # Fetch article data from database
    import subprocess
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
    
    print(f"Scoring {len(articles)} articles...\n")
    
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
            cost = (result['input_tokens'] / 1_000_000 * 2.50) + (result['output_tokens'] / 1_000_000 * 10.00)
            total_cost += cost
            print(f"Article {result['article_id']}: Score = {result['score']}")
            print(f"  Tokens: {result['total_tokens']} (in: {result['input_tokens']}, out: {result['output_tokens']})")
            print(f"  Cost: ${cost:.6f}")
            print()
    
    print("-" * 60)
    print(f"Total cost: ${total_cost:.6f} (${total_cost * 100:.2f} cents)")
    print(f"Average cost per article: ${total_cost / len(results):.6f}")

if __name__ == "__main__":
    asyncio.run(main())

