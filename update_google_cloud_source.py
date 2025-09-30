#!/usr/bin/env python3
"""Update Google Cloud Threat Intelligence RSS URL without affecting other sources."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.database.manager import DatabaseManager
from src.models.source import SourceUpdate

def update_google_cloud_rss():
    """Update Google Cloud Threat Intelligence source RSS URL."""

    # Initialize database manager
    db = DatabaseManager()

    # Get the source by identifier
    source = db.get_source_by_identifier("google_cloud_threat_intel")

    if not source:
        print("❌ Error: google_cloud_threat_intel source not found in database")
        return False

    print(f"Found source ID {source.id}: {source.name}")
    print(f"Current RSS URL: {source.rss_url}")

    # New working RSS URL
    new_rss_url = "https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v"

    if source.rss_url == new_rss_url:
        print("✅ RSS URL is already up to date!")
        return True

    # Update the source
    update_data = SourceUpdate(rss_url=new_rss_url)

    try:
        updated_source = db.update_source(source.id, update_data)
        if updated_source:
            print(f"✅ Successfully updated RSS URL to: {new_rss_url}")
            print(f"Source ID {source.id} ({source.name}) is now fixed")
            return True
        else:
            print("❌ Failed to update source")
            return False
    except Exception as e:
        print(f"❌ Error updating source: {e}")
        return False

if __name__ == "__main__":
    success = update_google_cloud_rss()
    sys.exit(0 if success else 1)