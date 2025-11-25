#!/usr/bin/env python3
"""Get full extract results with observable details for all articles."""
import asyncio
import sys
import os
import subprocess
import json
import httpx
import re

API_KEY = "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"

async def extract_article_full(article_id: int, title: str, url: str, content: str, prompt_config_dict: dict, instructions_template: str) -> dict:
    """Extract observables and return full details."""
    prompt_config_json = json.dumps(prompt_config_dict, indent=2)
    user_prompt = instructions_template.format(
        title=title,
        url=url,
        content=content,
        prompt_config=prompt_config_json
    )
    
    system_content = prompt_config_dict.get('task', prompt_config_dict.get('role', 'You are a detection engineer LLM.'))
    
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
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 1200,
                "temperature": 0
            },
            timeout=180.0
        )
        
        if response.status_code != 200:
            raise Exception(f"API Error {response.status_code}: {response.text}")
        
        result = response.json()
        response_text = result['choices'][0]['message']['content'].strip()
        
        # Parse JSON
        code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
        if code_fence_match:
            json_text = code_fence_match.group(1).strip()
            extracted = json.loads(json_text)
        else:
            extracted = json.loads(response_text)
        
        return {
            'article_id': article_id,
            'title': title,
            'full_response': extracted,
            'observables': extracted.get('observables', []),
            'summary': extracted.get('summary', {}),
            'raw_response': response_text
        }

async def main():
    """Get full results for all articles."""
    article_ids = [1974, 1909, 1866, 1860, 1937, 1794]
    
    # Load prompt from database
    db_result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-c", 
         "SELECT agent_prompts->'ExtractAgent' FROM agentic_workflow_config WHERE is_active = true ORDER BY version DESC LIMIT 1;"],
        capture_output=True,
        text=True
    )
    
    agent_prompt_data = json.loads(db_result.stdout.strip())
    prompt_str = agent_prompt_data.get("prompt", "")
    prompt_config_dict = json.loads(prompt_str) if isinstance(prompt_str, str) else prompt_str
    instructions_template = agent_prompt_data.get("instructions", "")
    
    # Fetch articles
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-F", "|", "-c", 
         f"SELECT a.id, a.title, a.canonical_url, s.name, a.content FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id IN ({','.join(map(str, article_ids))}) ORDER BY id;"],
        capture_output=True,
        text=True
    )
    
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
    
    # Extract from all articles
    all_results = {}
    for article in articles:
        print(f"Extracting from article {article['id']}...")
        try:
            result = await extract_article_full(
                article_id=article['id'],
                title=article['title'],
                url=article['url'],
                content=article['content'],
                prompt_config_dict=prompt_config_dict,
                instructions_template=instructions_template
            )
            all_results[str(article['id'])] = result
            await asyncio.sleep(1)
        except Exception as e:
            print(f"  Error: {e}")
            all_results[str(article['id'])] = {'error': str(e)}
    
    # Save full results
    with open('gpt4o_extract_results_full.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("Full Extract Results Summary")
    print("=" * 80)
    
    for article_id in sorted([int(k) for k in all_results.keys()]):
        result = all_results[str(article_id)]
        if 'error' in result:
            print(f"\nArticle {article_id}: ERROR - {result['error']}")
            continue
        
        title = result.get('title', 'N/A')
        observables = result.get('observables', [])
        summary = result.get('summary', {})
        count = summary.get('count', len(observables))
        
        print(f"\n{'='*80}")
        print(f"Article {article_id}: {title}")
        print(f"{'='*80}")
        print(f"Observable Count: {count}")
        print(f"\nObservables:")
        
        for i, obs in enumerate(observables, 1):
            obs_type = obs.get('type', 'N/A')
            obs_value = obs.get('value', 'N/A')
            platform = obs.get('platform', 'N/A')
            source_context = obs.get('source_context', '')
            
            print(f"\n  {i}. Type: {obs_type}")
            print(f"     Value: {obs_value}")
            print(f"     Platform: {platform}")
            if source_context:
                print(f"     Context: {source_context}")
        
        print(f"\nSummary:")
        print(f"  Count: {summary.get('count', 'N/A')}")
        print(f"  Source URL: {summary.get('source_url', 'N/A')}")
        print(f"  Platforms: {summary.get('platforms_detected', [])}")
    
    print(f"\n\nFull results saved to: gpt4o_extract_results_full.json")

if __name__ == "__main__":
    asyncio.run(main())

