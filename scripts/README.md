# Scripts Directory

This directory contains utility scripts and testing tools for the CTI Scraper.

## Structure

```
scripts/
├── testing/           # Test and analysis scripts
│   ├── analyze_keywords.py
│   ├── check_missing_keywords.py
│   ├── check_source_urls.py
│   ├── debug_simple_search.py
│   ├── test_arrow_keyword.py
│   ├── test_keyword_fidelity.py
│   ├── test_lolbas_scoring.py
│   ├── test_new_keywords.py
│   ├── test_search_fix.py
│   └── test_threat_hunting_scoring.py
├── fix_epoch_dates.py # One-time utility for fixing date formats
└── README.md          # This file
```

## Testing Scripts

The `testing/` directory contains various test and analysis scripts:

- **Keyword Analysis**: Scripts for testing keyword matching and scoring
- **Search Testing**: Scripts for testing search functionality
- **Source Validation**: Scripts for checking source URLs and connectivity
- **Debug Tools**: Scripts for debugging specific issues

## Usage

Most scripts can be run directly:

```bash
# Run from project root
python scripts/testing/analyze_keywords.py
python scripts/testing/check_source_urls.py

# Or run from scripts directory
cd scripts/testing
python analyze_keywords.py
```

## Notes

- These scripts are primarily for development and testing
- Some may require the Docker environment to be running
- Check individual script documentation for specific requirements
