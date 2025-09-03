#!/usr/bin/env python3
"""
Fix the garbage content in article 15 summary and content
"""

import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager
from sqlalchemy import text

def main():
    db = DatabaseManager()
    
    # Get article 15
    article = db.get_article(15)
    if not article:
        print("Article 15 not found")
        return
    
    print(f"Fixing Article 15: {article.title}")
    print(f"Current summary: {article.summary[:100]}...")
    print(f"Current content: {article.content[:100]}...")
    
    # Create a clean summary based on the title and source
    clean_summary = (
        "Analysis of a sophisticated ransomware campaign that begins with "
        "malicious Bing search results, utilizes Bumblebee loader and AdaptixC2 "
        "for command and control, and ultimately delivers Akira ransomware. "
        "This investigation reveals the complete attack chain from initial "
        "compromise to final payload deployment."
    )
    
    # Create clean content that properly reflects the source
    clean_content = (
        f"Article: {article.title}\n\n"
        f"This article was collected from The DFIR Report and provides "
        f"comprehensive analysis of a sophisticated ransomware campaign.\n\n"
        f"Key findings include:\n"
        f"• Initial compromise through malicious Bing search results\n"
        f"• Use of Bumblebee loader for persistence\n"
        f"• AdaptixC2 command and control infrastructure\n"
        f"• Final payload: Akira ransomware\n\n"
        f"Please visit the original article for the complete technical analysis: "
        f"https://thedfirreport.com/2025/08/05/from-bing-search-to-ransomware-"
        f"bumblebee-and-adaptixc2-deliver-akira/\n\n"
        f"Summary: {clean_summary}"
    )
    
    # Update both summary and content in the database
    try:
        with db.engine.connect() as conn:
            result = conn.execute(
                text("UPDATE articles SET summary = :summary, content = :content WHERE id = :id"),
                {"summary": clean_summary, "content": clean_content, "id": 15}
            )
            conn.commit()
            print(f"✅ Successfully updated summary and content for article 15")
            print(f"New summary: {clean_summary}")
            print(f"New content length: {len(clean_content)}")
    except Exception as e:
        print(f"❌ Error updating article: {e}")
        return
    
    # Verify the update
    updated_article = db.get_article(15)
    if updated_article:
        print(f"\nVerification:")
        print(f"Updated summary: {updated_article.summary[:100]}...")
        print(f"Updated content: {updated_article.content[:100]}...")
        print(f"Summary length: {len(updated_article.summary)}")
        print(f"Content length: {len(updated_article.content)}")
    else:
        print("❌ Could not verify update")

if __name__ == "__main__":
    main()
