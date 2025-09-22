# CTIScraper Browser Extension

A browser extension that allows you to send articles directly to your CTIScraper instance for threat intelligence analysis.

## Features

- **One-click scraping**: Send any article to CTIScraper with a single click
- **Smart content extraction**: Automatically extracts article title and content
- **Duplicate detection**: Respects existing articles unless forced
- **Direct integration**: Works with your local CTIScraper API
- **Clean interface**: Simple, intuitive popup interface

## Installation

1. **Load the extension**:
   - Open Chrome/Edge and go to `chrome://extensions/`
   - Enable "Developer mode" (toggle in top right)
   - Click "Load unpacked" and select the `browser-extension` folder

2. **Configure the API URL**:
   - Click the extension icon in your browser toolbar
   - Set the CTIScraper API URL (default: `http://127.0.0.1:8000`)
   - Configure other settings as needed

## Usage

1. **Navigate to any article** you want to analyze
2. **Click the CTIScraper extension icon** in your browser toolbar
3. **Review the extracted content** (title, URL, word count)
4. **Click "Send to CTIScraper"** to scrape the article
5. **View the results** - the extension will open the article in CTIScraper

## How It Works

The extension works exactly like your manual URL scraping interface:

1. **Content Extraction**: Extracts article title and content from the current page
2. **API Call**: Sends a POST request to `/api/scrape-url` with:
   - `url`: Current page URL
   - `title`: Extracted or custom title
   - `force_scrape`: Whether to ignore duplicates
3. **Processing**: CTIScraper processes the article with threat hunting scoring
4. **Results**: Opens the processed article in CTIScraper

## Configuration Options

- **API URL**: Your CTIScraper instance URL (default: `http://127.0.0.1:8000`)
- **Force Scrape**: Whether to scrape even if the URL already exists
- **Auto-open**: Automatically opens the processed article in CTIScraper

## Supported Sites

The extension works on most websites with articles, including:
- News websites
- Blog posts
- Security research articles
- Threat intelligence reports
- Technical documentation

## Troubleshooting

**Extension not working?**
- Check that CTIScraper is running on the configured API URL
- Verify the API URL is correct in the extension settings
- Check browser console for error messages

**Content not extracted properly?**
- Some sites may have complex layouts
- Try refreshing the page and clicking the extension again
- The extension will fall back to using the page title and body content

**API errors?**
- Ensure CTIScraper is running and accessible
- Check that the `/api/scrape-url` endpoint is working
- Verify network connectivity to your CTIScraper instance

**Non-routable IP error?**
- The extension blocks ingestion from private/local IP addresses (127.0.0.1, 192.168.x.x, etc.)
- This prevents accidental ingestion of internal documentation or local content
- Use public URLs or domain names instead of IP addresses
- If you need to ingest from a private IP, contact your administrator

## Development

To modify the extension:

1. **Edit files** in the `browser-extension` folder
2. **Reload the extension** in `chrome://extensions/`
3. **Test changes** by clicking the extension icon

### File Structure

```
browser-extension/
├── manifest.json      # Extension configuration
├── popup.html        # Extension popup interface
├── popup.js          # Popup functionality
├── content.js        # Content script for page extraction
├── background.js     # Background script for API calls
└── icons/           # Extension icons (placeholder)
```

## Security

- The extension only communicates with your configured CTIScraper instance
- No data is sent to external services
- All API calls are made directly to your local/configured server
- Content extraction happens locally in your browser
- **Non-routable IP protection**: The extension prevents ingestion from non-routable IP addresses (127.0.0.1, 192.168.x.x, 10.x.x.x, etc.) to prevent accidental ingestion of local/internal content
