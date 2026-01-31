#!/usr/bin/env python3
"""
Export highlighted text classifications to CSV
Usage: python scripts/export_highlights.py [output_file]
"""

import os
import subprocess
import sys
from datetime import datetime


def export_highlights(output_file=None):
    """Export highlighted text classifications to CSV"""

    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"highlighted_text_classifications_{timestamp}.csv"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)

    # SQL query to export data
    sql_query = """
    COPY (
      SELECT 
        ROW_NUMBER() OVER (ORDER BY th.created_at) as record_number,
        th.selected_text as highlighted_text,
        CASE 
          WHEN th.is_huntable = true THEN 'Huntable'
          WHEN th.is_huntable = false THEN 'Not Huntable'
          ELSE 'Unknown'
        END as classification,
        a.title as article_title,
        th.created_at as classification_date
      FROM text_highlights th
      LEFT JOIN articles a ON th.article_id = a.id
      ORDER BY th.created_at
    ) TO STDOUT WITH CSV HEADER;
    """

    try:
        # Execute the PostgreSQL command
        cmd = ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", "-c", sql_query]

        with open(output_file, "w") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0:
            # Count lines to verify export
            with open(output_file) as f:
                lines = f.readlines()

            record_count = len(lines) - 1  # Subtract header
            print(f"✅ Successfully exported {record_count} highlighted text classifications")
            print(f"📁 File saved: {os.path.abspath(output_file)}")

            # Show summary
            huntable_count = sum(1 for line in lines[1:] if ",Huntable" in line)
            not_huntable_count = sum(1 for line in lines[1:] if ",Not Huntable" in line)

            print("📊 Summary:")
            print(f"   - Huntable: {huntable_count}")
            print(f"   - Not Huntable: {not_huntable_count}")
            print(f"   - Total: {record_count}")

        else:
            print(f"❌ Export failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error during export: {e}")
        return False

    return True


if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    export_highlights(output_file)
