# Google Custom Search API Setup Instructions

## 1. Create Google Custom Search Engine

1. Go to [Google Custom Search Engine](https://cse.google.com/cse/)
2. Click "Add" to create a new search engine
3. Configure:
   - **Sites to search**: Leave blank (search entire web)
   - **Language**: English
   - **Name**: "CTI Scraper Threat Intelligence"

## 2. Get API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "Custom Search API"
4. Go to "Credentials" → "Create Credentials" → "API Key"
5. Copy the API key

## 3. Get Search Engine ID

1. Go back to [Google Custom Search Engine](https://cse.google.com/cse/)
2. Click on your search engine
3. Go to "Setup" → "Basics"
4. Copy the "Search engine ID" (looks like: `017576662512468239146:omuauf_lfve`)

## 4. Configure Environment Variables

Add to your `.env` file or environment:

```bash
GOOGLE_SEARCH_API_KEY=your_api_key_here
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id_here
```

## 5. Test Configuration

Run the test script to verify setup:

```bash
python test_google_search.py
```

## 6. Usage Limits

- **Free Tier**: 100 queries/day
- **Paid**: $5 per 1,000 queries
- **Current Config**: ~50 queries/day (well within free tier)

## 7. Customization

Edit `config/sources.yaml` to modify:
- Search queries
- Site restrictions  
- Date ranges
- Result limits

## Troubleshooting

- **403 Error**: Check API key and enable Custom Search API
- **400 Error**: Verify search engine ID format
- **No Results**: Adjust queries or site restrictions
