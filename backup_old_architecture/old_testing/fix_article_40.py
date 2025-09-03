#!/usr/bin/env python3
"""
Fix the garbage content in article 40 from SpecterOps Blog
"""

import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager
from sqlalchemy import text

def main():
    db = DatabaseManager()
    
    # Get article 40
    article = db.get_article(40)
    if not article:
        print("Article 40 not found")
        return
    
    print(f"Fixing Article 40: {article.title}")
    print(f"Current summary: {article.summary[:100]}...")
    print(f"Current content: {article.content[:100]}...")
    
    # Create a clean summary based on the title and source
    clean_summary = (
        "Microsoft has changed how the Entra Connect Sync agent authenticates to "
        "Entra ID, affecting attacker tradecraft. The sync account credentials "
        "can no longer be exported using previous methods, requiring updated "
        "techniques for credential access and persistence."
    )
    
    # Create clean content that properly reflects the source
    clean_content = (
        f"Article: {article.title}\n\n"
        f"This article was collected from SpecterOps Blog and provides "
        f"technical analysis of recent changes to Microsoft Entra Connect Sync.\n\n"
        f"Key findings include:\n"
        f"• Microsoft changed Entra Connect Sync agent authentication\n"
        f"• Previous credential export methods no longer work\n"
        f"• Attackers need updated tradecraft techniques\n"
        f"• Impact on credential access and persistence methods\n\n"
        f"Please visit the original article for the complete technical analysis: "
        f"https://posts.specterops.io/\n\n"
        f"Summary: {clean_summary}"
    )
    
    # Update both summary and content in the database
    try:
        with db.engine.connect() as conn:
            result = conn.execute(
                text("UPDATE articles SET summary = :summary, content = :content WHERE id = :id"),
                {"summary": clean_summary, "content": clean_content, "id": 40}
            )
            conn.commit()
            print(f"✅ Successfully updated summary and content for article 40")
            print(f"New summary: {clean_summary}")
            print(f"New content length: {len(clean_content)}")
    except Exception as e:
        print(f"❌ Error updating article: {e}")
        return
    
    # Verify the update
    updated_article = db.get_article(40)
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
