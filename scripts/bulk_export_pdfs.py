#!/usr/bin/env python3
"""
Bulk export PDFs for specified articles with Perfect and LOLBAS highlights.
"""

import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
except ImportError:
    print("ERROR: reportlab is not installed.")
    print("Please install it using one of these methods:")
    print("  1. pip install reportlab")
    print("  2. Add 'reportlab' to requirements.txt and install dependencies")
    print("  3. If using Docker: docker exec -it <container> pip install reportlab")
    sys.exit(1)

from src.database.manager import DatabaseManager
from src.web.utils.jinja_filters import highlight_keywords

# Article IDs and titles
ARTICLES = [
    (603, "From Bing Search to Ransomware: Bumblebee and AdaptixC2 Deliver Akira"),
    (632, "Under the Pure Curtain: From RAT to Builder to Coder"),
    (633, "Yurei & The Ghost of Open Source Ransomware"),
    (640, "Agentic Frameworks Summary"),
    (642, "Massive npm infection: the Shai-Hulud worm and patient zero"),
    (659, "Dissecting PipeMagic: Inside the architecture of a modular backdoor framework"),
    (836, "Crypto24 Ransomware Uncovered: Stealth, Persistence, and Enterprise-Scale Impact"),
    (846, "What is Protected Health Information (PHI) ?"),
    (979, "Think before you Click(Fix): Analyzing the ClickFix social engineering technique"),
    (980, "Dissecting PipeMagic: Inside the architecture of a modular backdoor framework"),
    (1298, "UAT-8099: Chinese-speaking cybercrime group targets high-value IIS for SEO fraud"),
    (1443, "XWorm malware resurfaces with ransomware module, over 35 plugins"),
    (1446, "Detecting DLL hijacking with machine learning: real-world cases"),
    (1447, "Europol Calls for Stronger Data Laws to Combat Cybercrime"),
    (1452, "Investigating active exploitation of CVE-2025-10035 GoAnywhere Managed File Transfer vulnerability"),
    (2055, "CABINETRAT Malware Windows Targeted Campaign Explained"),
    (2063, "CVE-2025-59287 Explained: WSUS Unauthenticated RCE Vulnerability"),
    # Rejected articles
    (637, "Before ToolShell: Exploring Storm-2603's Previous Ransomware Operations"),
    (638, "MCP Tools: Attack Vectors and Defense Recommendations for Autonomous Agents"),
    (1547, "Severe Figma MCP Vulnerability Lets Hackers Execute Code Remotely — Patch Now"),
]

# Save to root directory (in Docker, /app maps to project root)
OUTPUT_DIR = Path("/app") if Path("/app").exists() else project_root


def sanitize_filename(title: str) -> str:
    """Sanitize title for use as filename."""
    filename = re.sub(r"[^\w\s-]", "", title)
    filename = re.sub(r"[-\s]+", "_", filename)
    return filename[:100]


def parse_html_to_paragraphs(html_content: str, styles) -> list:
    """
    Parse HTML content with highlights and convert to ReportLab Paragraphs.
    Only preserves Perfect (green) and LOLBAS (blue) highlights.
    """
    from html.parser import HTMLParser

    from reportlab.platypus import Paragraph

    class HighlightParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.elements = []
            self.current_text = []
            self.in_highlight = False
            self.highlight_type = None

        def handle_starttag(self, tag, attrs):
            if tag == "span":
                # Check for highlight classes
                attrs_dict = dict(attrs)
                classes = attrs_dict.get("class", "").split()

                # Check for Perfect (green) or LOLBAS (blue) highlights
                if "bg-green-100" in classes or "bg-green-200" in classes or "bg-green-300" in classes:
                    self.in_highlight = True
                    self.highlight_type = "perfect"
                elif "bg-blue-100" in classes or "bg-blue-200" in classes:
                    self.in_highlight = True
                    self.highlight_type = "lolbas"
                # Ignore purple and orange highlights
                elif "bg-purple" in " ".join(classes) or "bg-orange" in " ".join(classes):
                    self.in_highlight = True
                    self.highlight_type = None  # Will be treated as plain text
                else:
                    self.in_highlight = False
                    self.highlight_type = None
            else:
                self.in_highlight = False
                self.highlight_type = None

        def handle_endtag(self, tag):
            if tag == "span" and self.in_highlight:
                self.in_highlight = False
                self.highlight_type = None

        def handle_data(self, data):
            if self.in_highlight and self.highlight_type:
                # Add highlighted text
                if self.highlight_type == "perfect":
                    # Green highlight
                    style = ParagraphStyle(
                        "PerfectHighlight",
                        parent=styles["Normal"],
                        backColor=HexColor("#d1fae5"),
                        textColor=HexColor("#065f46"),
                        borderPadding=2,
                        borderWidth=1,
                        borderColor=HexColor("#10b981"),
                    )
                else:  # lolbas
                    # Blue highlight
                    style = ParagraphStyle(
                        "LOLBASHighlight",
                        parent=styles["Normal"],
                        backColor=HexColor("#dbeafe"),
                        textColor=HexColor("#1e40af"),
                        borderPadding=2,
                        borderWidth=1,
                        borderColor=HexColor("#3b82f6"),
                    )
                # Escape XML special chars and create paragraph
                escaped_data = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                self.elements.append(Paragraph(escaped_data, style))
            else:
                # Regular text
                if data.strip():
                    escaped_data = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    self.elements.append(Paragraph(escaped_data, styles["Normal"]))

    parser = HighlightParser()
    parser.feed(html_content)
    return parser.elements


def create_pdf(article_id: int, title: str, content: str, metadata: dict, output_path: Path):
    """Create a PDF for an article with highlights."""
    print(f"  Creating PDF for article {article_id}...")

    # Apply highlighting (same as web interface)
    highlighted_content = highlight_keywords(content, metadata or {})

    # Create PDF
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=20 * mm, bottomMargin=20 * mm
    )

    # Build story
    story = []
    styles = getSampleStyleSheet()

    # Title style
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=HexColor("#000000"),
        spaceAfter=20,
        alignment=TA_LEFT,
    )

    # Add title
    story.append(Paragraph(title.replace("&", "&amp;"), title_style))
    story.append(Spacer(1, 12))

    # Content style (monospace like web)
    content_style = ParagraphStyle(
        "Content",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Courier",
        textColor=HexColor("#000000"),
        leading=18,
        alignment=TA_LEFT,
    )
    styles.add(content_style)

    # Parse HTML and convert to paragraphs
    # Simple approach: split by highlights and process
    # Extract text with highlights
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.current_text = ""
            self.in_highlight = False
            self.highlight_class = None

        def handle_starttag(self, tag, attrs):
            if tag == "span":
                # Save current text if any
                if self.current_text:
                    self.parts.append(("text", self.current_text))
                    self.current_text = ""

                attrs_dict = dict(attrs)
                classes = attrs_dict.get("class", "").split()

                if "bg-green-100" in classes or "bg-green-200" in classes or "bg-green-300" in classes:
                    self.in_highlight = True
                    self.highlight_class = "perfect"
                elif "bg-blue-100" in classes or "bg-blue-200" in classes:
                    self.in_highlight = True
                    self.highlight_class = "lolbas"
                else:
                    self.in_highlight = False
                    self.highlight_class = None
            else:
                if self.current_text:
                    self.parts.append(("text", self.current_text))
                    self.current_text = ""
                self.in_highlight = False
                self.highlight_class = None

        def handle_endtag(self, tag):
            if tag == "span" and self.in_highlight:
                if self.current_text:
                    self.parts.append((self.highlight_class, self.current_text))
                    self.current_text = ""
                self.in_highlight = False
                self.highlight_class = None

        def handle_data(self, data):
            self.current_text += data

    # Parse HTML
    extractor = TextExtractor()
    extractor.feed(highlighted_content)

    # Add any remaining text
    if extractor.current_text:
        extractor.parts.append(("text", extractor.current_text))

    # Create paragraphs with highlights
    for part_type, text in extractor.parts:
        if not text.strip():
            continue

        # Escape XML
        escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if part_type == "perfect":
            # Green highlight
            highlight_style = ParagraphStyle(
                "PerfectHighlight",
                parent=content_style,
                backColor=HexColor("#d1fae5"),
                textColor=HexColor("#065f46"),
                borderPadding=2,
                borderWidth=1,
                borderColor=HexColor("#10b981"),
            )
            story.append(Paragraph(escaped_text, highlight_style))
        elif part_type == "lolbas":
            # Blue highlight
            highlight_style = ParagraphStyle(
                "LOLBASHighlight",
                parent=content_style,
                backColor=HexColor("#dbeafe"),
                textColor=HexColor("#1e40af"),
                borderPadding=2,
                borderWidth=1,
                borderColor=HexColor("#3b82f6"),
            )
            story.append(Paragraph(escaped_text, highlight_style))
        else:
            # Regular text
            story.append(Paragraph(escaped_text, content_style))

    # Build PDF
    doc.build(story)
    print(f"  ✅ PDF created: {output_path.name}")


def bulk_export_pdfs(articles: list[tuple[int, str]], output_dir: Path = OUTPUT_DIR):
    """Bulk export PDFs for all articles."""
    print(f"🚀 Starting bulk PDF export for {len(articles)} articles")
    print(f"📁 Output directory: {output_dir.absolute()}")

    db_manager = DatabaseManager()
    results = []

    for i, (article_id, title) in enumerate(articles, 1):
        print(f"\n[{i}/{len(articles)}] Processing article {article_id}: {title[:60]}...")

        try:
            # Get article from database (including archived)
            from src.database.models import ArticleTable

            session = db_manager.get_session()
            try:
                db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not db_article:
                    results.append((article_id, title, False, "Article not found"))
                    print("  ❌ Article not found")
                    continue

                # Convert to Article model
                article = db_manager._db_article_to_model(db_article)
            finally:
                session.close()

            # Get metadata
            metadata = article.article_metadata if hasattr(article, "article_metadata") else {}
            if not metadata:
                # Try to get from database directly
                from src.database.models import ArticleTable

                session = db_manager.get_session()
                try:
                    db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                    if db_article:
                        metadata = db_article.article_metadata or {}
                finally:
                    session.close()

            # Create filename
            safe_title = sanitize_filename(title)
            filename = f"article_{article_id}_{safe_title}.pdf"
            output_path = output_dir / filename

            # Create PDF
            create_pdf(article_id, title, article.content, metadata, output_path)

            # Verify file
            if output_path.exists() and output_path.stat().st_size > 0:
                file_size = output_path.stat().st_size
                results.append((article_id, title, True, f"PDF saved: {filename} ({file_size:,} bytes)"))
            else:
                results.append((article_id, title, False, "PDF file is empty or not created"))

        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ Error: {error_msg}")
            results.append((article_id, title, False, f"Error: {error_msg}"))

    # Print summary
    print("\n" + "=" * 80)
    print("📊 Export Summary")
    print("=" * 80)

    successful = [r for r in results if r[2]]
    failed = [r for r in results if not r[2]]

    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    for article_id, title, _, msg in successful:
        print(f"   {article_id}: {title[:50]}")

    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for article_id, title, _, msg in failed:
            print(f"   {article_id}: {title[:50]} - {msg}")

    print(f"\n📁 PDFs saved to: {output_dir.absolute()}")
    return results


if __name__ == "__main__":
    bulk_export_pdfs(ARTICLES, OUTPUT_DIR)
