"""Content processing utilities."""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from dateutil import parser as date_parser
import hashlib
from bs4 import BeautifulSoup, Tag
# Temporarily disabled due to Python 3 compatibility issues
# from readability import Document
import logging
from .sentence_splitter import split_sentences

logger = logging.getLogger(__name__)


class ContentCleaner:
    """Utility class for cleaning and normalizing content."""
    
    @staticmethod
    def clean_html(html: str) -> str:
        """Clean HTML content and extract readable text."""
        # Temporarily disabled readability due to Python 3 compatibility issues
        # Always use enhanced cleaning for now
        return ContentCleaner.enhanced_html_clean(html)
    
    @staticmethod
    def enhanced_html_clean(html: str) -> str:
        """Enhanced HTML cleaning that extracts clean text."""
        if not html:
            return ""
            
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements completely
        unwanted_tags = [
            "script", "style", "nav", "header", "footer", "aside", 
            "advertisement", "menu", "sidebar", "breadcrumb", "pagination",
            "social", "share", "comment", "related", "widget", "promo",
            "banner", "ad", "popup", "modal", "overlay", "tracking", "form"
        ]
        
        for tag_name in unwanted_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        # Remove elements by class/id patterns (common navigation/UI elements)
        unwanted_patterns = [
            'nav', 'menu', 'sidebar', 'header', 'footer', 'breadcrumb',
            'pagination', 'social', 'share', 'comment', 'related', 'widget',
            'promo', 'banner', 'ad', 'popup', 'modal', 'overlay', 'tracking',
            'subscribe', 'newsletter', 'follow', 'like', 'tweet', 'facebook',
            'advertisement', 'comments'
        ]
        
        for pattern in unwanted_patterns:
            for element in soup.find_all(attrs={'class': lambda x: x and any(pattern.lower() in str(x).lower() for pattern in unwanted_patterns)}):
                element.decompose()
            for element in soup.find_all(attrs={'id': lambda x: x and any(pattern.lower() in str(x).lower() for pattern in unwanted_patterns)}):
                element.decompose()
        
        # Find main content area
        content_selectors = [
            'article', '[role="main"]', 'main', '.content', '.post-content',
            '.entry-content', '.blog-content', '.article-content', '#content'
        ]
        
        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content and len(main_content.get_text(strip=True)) > 50:  # Lower threshold
                break
        
        if main_content:
            # Extract clean text from main content
            return ContentCleaner.html_to_text(str(main_content))
        else:
            # Fallback: extract from body but clean aggressively
            return ContentCleaner.html_to_text(str(soup))
    
    @staticmethod
    def basic_html_clean(html: str) -> str:
        """Basic HTML cleaning without readability (deprecated - use enhanced_html_clean)."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "advertisement"]):
            tag.decompose()
        
        # Remove attributes that might cause issues
        for tag in soup.find_all():
            tag.attrs = {k: v for k, v in tag.attrs.items() 
                        if k in ['href', 'src', 'alt', 'title']}
        
        return str(soup)
    
    @staticmethod
    def html_to_text(html: str) -> str:
        """Convert HTML to clean text with better formatting."""
        try:
            # Ensure we have clean text input
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            soup = BeautifulSoup(html, 'lxml')
            
            # Add line breaks for block elements before extracting text
            for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br']):
                tag.insert_after('\n')
            
            # Extract text
            text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace and normalize
            text = ContentCleaner.normalize_whitespace(text)
            
            # Remove non-printable characters
            text = ContentCleaner.clean_text_characters(text)
            
            return text
        except Exception as e:
            logger.warning(f"Error in html_to_text: {e}")
            # Fallback to simple text extraction
            return ContentCleaner.normalize_whitespace(str(html))
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple whitespace characters with single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    @staticmethod
    def clean_text_characters(text: str) -> str:
        """Clean text by removing non-printable and control characters."""
        try:
            # First, ensure we have proper UTF-8 encoding
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            
            # Remove Unicode replacement characters ()
            text = text.replace('\ufffd', '')
            
            # Remove control characters and other problematic characters
            # Keep only printable ASCII and common Unicode characters
            cleaned = ''.join(char for char in text if (
                char.isprintable() or char.isspace()
            ) and ord(char) < 65536)  # Basic Multilingual Plane
            
            # Remove any remaining problematic sequences
            cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned)
            
            # Fix common UTF-8 to Latin-1 corruption patterns
            # Fix possessive apostrophes: ‚Äö√Ñ√¥s -> 's
            cleaned = re.sub(r'‚Äö√Ñ√¥s', "'s", cleaned)
            cleaned = re.sub(r'‚Äö√Ñ√¥', "'", cleaned)
            
            # Additional cleanup for other encoding issues
            cleaned = re.sub(r'[^\x00-\x7F]+', ' ', cleaned)  # Replace remaining non-ASCII with spaces
            
            return cleaned
        except Exception as e:
            logger.warning(f"Error cleaning text characters: {e}")
            # Fallback: remove only null bytes and common control chars
            return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    @staticmethod
    def extract_summary(content: str, max_length: int = 500) -> str:
        """Extract summary from content."""
        # Convert HTML to text if needed
        if '<' in content and '>' in content:
            text = ContentCleaner.html_to_text(content)
        else:
            text = content
        
        # Normalize whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        # Find first complete sentence that doesn't exceed max_length
        sentences = split_sentences(text)
        summary = ""
        
        for sentence in sentences:
            if not sentence:
                continue
            
            test_summary = f"{summary} {sentence}".strip()
            if len(test_summary) <= max_length:
                summary = test_summary
            else:
                break
        
        # If no complete sentences fit, truncate at word boundary
        if not summary:
            words = text.split()
            summary = ""
            for word in words:
                test_summary = f"{summary} {word}".strip()
                if len(test_summary) <= max_length - 3:  # Leave room for "..."
                    summary = test_summary
                else:
                    break
            summary += "..."
        
        return summary
    
    @staticmethod
    def calculate_content_hash(title: str, content: str) -> str:
        """Calculate SHA256 hash of content for deduplication."""
        # Normalize content for hashing
        normalized_title = ContentCleaner.normalize_whitespace(title.lower())
        normalized_content = ContentCleaner.normalize_whitespace(
            ContentCleaner.html_to_text(content).lower()
        )
        
        combined = f"{normalized_title}\n{normalized_content}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()


class DateExtractor:
    """Utility class for extracting and parsing dates."""
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        try:
            # Handle common date formats
            date_str = date_str.strip()
            
            # Parse the date (may be timezone-aware)
            parsed_date = date_parser.parse(date_str)
            
            # Convert to timezone-naive datetime for database compatibility
            if parsed_date.tzinfo is not None:
                # Convert to UTC first, then remove timezone info
                parsed_date = parsed_date.astimezone().replace(tzinfo=None)
            
            return parsed_date
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
            return None
    
    @staticmethod
    def extract_date_from_url(url: str) -> Optional[datetime]:
        """Extract date from URL path if possible."""
        # Look for YYYY/MM/DD or YYYY-MM-DD patterns
        date_patterns = [
            r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 2024/01/15
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2024-01-15
            r'(\d{4})(\d{2})(\d{2})',        # 20240115
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year, month, day = map(int, match.groups())
                    return datetime(year, month, day)
                except ValueError:
                    continue
        
        return None


class MetadataExtractor:
    """Utility class for extracting metadata from HTML."""
    
    @staticmethod
    def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract all meta tag content."""
        meta_data = {}
        
        # Standard meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property') or meta.get('http-equiv')
            content = meta.get('content')
            
            if name and content:
                meta_data[name.lower()] = content
        
        return meta_data
    
    @staticmethod
    def extract_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract OpenGraph metadata."""
        og_data = {}
        
        for meta in soup.find_all('meta'):
            property_name = meta.get('property', '')
            if property_name.startswith('og:'):
                content = meta.get('content')
                if content:
                    key = property_name[3:]  # Remove 'og:' prefix
                    og_data[key] = content
        
        return og_data
    
    @staticmethod
    def extract_twitter_cards(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter Card metadata."""
        twitter_data = {}
        
        for meta in soup.find_all('meta'):
            name = meta.get('name', '')
            if name.startswith('twitter:'):
                content = meta.get('content')
                if content:
                    key = name[8:]  # Remove 'twitter:' prefix
                    twitter_data[key] = content
        
        return twitter_data
    
    @staticmethod
    def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL from link tag."""
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical:
            return canonical.get('href')
        return None
    
    @staticmethod
    def extract_authors(soup: BeautifulSoup) -> List[str]:
        """Extract author information from various sources."""
        authors = []
        
        # Try meta tags first
        author_meta = soup.find('meta', {'name': 'author'})
        if author_meta:
            content = author_meta.get('content', '')
            if content:
                # Split on common delimiters
                for delimiter in [',', ';', '&', ' and ']:
                    if delimiter in content:
                        authors.extend([a.strip() for a in content.split(delimiter)])
                        break
                else:
                    authors.append(content.strip())
        
        # Try OpenGraph
        if not authors:
            og_author = soup.find('meta', {'property': 'article:author'})
            if og_author:
                content = og_author.get('content', '').strip()
                if content:
                    authors.append(content)
        
        # Try structured data (basic)
        if not authors:
            # Look for author in JSON-LD or microdata
            author_elements = soup.find_all(attrs={'itemprop': 'author'})
            for elem in author_elements:
                if elem.string:
                    authors.append(elem.string.strip())
        
        # Clean and deduplicate
        cleaned_authors = []
        for author in authors:
            author = author.strip()
            if author and author not in cleaned_authors:
                cleaned_authors.append(author)
        
        return cleaned_authors[:5]  # Limit to 5 authors
    
    @staticmethod
    def extract_tags(soup: BeautifulSoup) -> List[str]:
        """Extract tags/categories from various sources."""
        tags = set()
        
        # Meta keywords
        keywords_meta = soup.find('meta', {'name': 'keywords'})
        if keywords_meta:
            content = keywords_meta.get('content', '')
            if content:
                tags.update([tag.strip() for tag in content.split(',') if tag.strip()])
        
        # OpenGraph tags
        og_tags = soup.find_all('meta', {'property': 'article:tag'})
        for tag_meta in og_tags:
            content = tag_meta.get('content', '').strip()
            if content:
                tags.add(content)
        
        # Category meta
        category_meta = soup.find('meta', {'name': 'category'})
        if category_meta:
            content = category_meta.get('content', '').strip()
            if content:
                tags.add(content)
        
        # Convert to sorted list and limit
        return sorted(list(tags))[:10]  # Limit to 10 tags


def validate_content(title: str, content: str, url: str, source_config: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Validate content and return list of issues.
    
    Args:
        title: Article title
        content: Article content
        url: Article URL
        source_config: Optional source configuration dict containing min_content_length
        
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    if not title or not title.strip():
        issues.append("Missing or empty title")
    elif len(title.strip()) < 5:
        issues.append("Title too short")
    elif len(title.strip()) > 500:
        issues.append("Title too long")
    
    if not content or not content.strip():
        issues.append("Missing or empty content")
    else:
        # Check for garbage content patterns
        if _is_garbage_content(content):
            issues.append("Content appears to be garbage/compressed data")
        
        # Check for compression failure messages
        if _has_compression_failure_indicators(content):
            issues.append("Content indicates extraction failure")
        
        text_content = ContentCleaner.html_to_text(content)
        content_length = len(text_content.strip())
        
        # Use source-specific minimum content length if configured
        min_length = 200  # Default minimum
        if source_config and 'min_content_length' in source_config:
            min_length = source_config['min_content_length']
        
        if content_length < min_length:
            issues.append(f"Content too short (minimum {min_length} chars, found {content_length})")
    
    if not url or not url.strip():
        issues.append("Missing URL")
    elif not url.startswith(('http://', 'https://')):
        issues.append("Invalid URL format")
    
    return issues

def _is_garbage_content(content: str) -> bool:
    """
    Detect if content is garbage/compressed data.
    
    Returns:
        True if content appears to be garbage
    """
    if not content:
        return False
    
    # Convert to lowercase for analysis
    content_lower = content.lower()
    
    # Check for high ratio of problematic characters
    problematic_chars = sum(1 for c in content if c in '[]{}|\\')
    total_chars = len(content)
    
    if total_chars > 0:
        problematic_ratio = problematic_chars / total_chars
        if problematic_ratio > 0.15:  # Increase threshold to 15% problematic characters
            # High problematic ratio detected
            return True
    
    # Check for specific garbage patterns
    if '`E9 UI=' in content or 'cwCz _9hvtYfL' in content:
        # Specific garbage patterns found
        return True
    
    # Check for consecutive problematic characters
    consecutive_count = 0
    max_consecutive = 0
    for char in content:
        if char in '[]{}|\\':
            consecutive_count += 1
            max_consecutive = max(max_consecutive, consecutive_count)
        else:
            consecutive_count = 0
    
    # Check final sequence
    if consecutive_count >= 3:
        max_consecutive = max(max_consecutive, consecutive_count)
    
    if max_consecutive >= 5:  # Increase threshold to 5 or more consecutive problematic chars
        # Too many consecutive problematic chars detected
        return True
    
    # Check for binary-like patterns (very permissive - only flag truly problematic sequences)
    binary_patterns = [
        r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\xFF]{10,}',  # Control characters and high-bit chars in long sequences
        r'[^\w\s\.\,\;\:\!\?\(\)\-\+\=\<\>\/\"\'\[\]\{\}\|\\\~\#\$\%\^\&\*\_\`\@]{15,}',  # Very long sequences of truly unusual chars
    ]
    
    import re
    for pattern in binary_patterns:
        matches = re.findall(pattern, content)
        if matches:
            # Binary pattern matches detected
            return True
    
    # Check for compression artifacts
    compression_indicators = [
        'compression issues',
        'website compression',
        'content extraction failed',
        'failed due to website',
        'compression failed',
        'extraction disabled'
    ]
    
    if any(indicator in content_lower for indicator in compression_indicators):
        logger.debug("Compression indicators found")
        return True
    
    return False

def _has_compression_failure_indicators(content: str) -> bool:
    """
    Check if content contains indicators of extraction failure.
    
    Returns:
        True if content suggests extraction failed
    """
    if not content:
        return False
    
    content_lower = content.lower()
    
    # Patterns that indicate extraction failure
    failure_patterns = [
        'content extraction failed',
        'failed due to website compression',
        'extraction is disabled',
        'please visit the original article',
        'compression issues',
        'website compression issues',
        'full content extraction is disabled'
    ]
    
    return any(pattern in content_lower for pattern in failure_patterns)


# Windows Malware Keywords for Threat Hunting Scoring
WINDOWS_MALWARE_KEYWORDS = {
        'perfect_discriminators': [
            'rundll32.exe', 'comspec', 'msiexec.exe', 'wmic.exe', 'iex', 'findstr.exe',
            'hklm', 'appdata', 'programdata', 'powershell.exe', 'wbem',
            '.lnk', 'D:\\', 'C:\\', '.iso', '<Command>', 'MZ',
            'svchost.exe', '-accepteula', 'lsass.exe', 'WINDIR', 'wintmp',
            '\\temp\\', '\\pipe\\', '%WINDIR%', '%wintmp%', 'FromBase64String',
            'MemoryStream', 'New-Object', 'DownloadString', 'Defender query',
            'sptth',
            # Promoted from LOLBAS (100% avg scores in high-scoring articles)
            'reg.exe', 'winlogon.exe', 'conhost.exe', 'msiexec.exe', 'wscript.exe', 'services.exe', 'fodhelper',
            # Promoted from Good discriminators (100% avg scores)
            'EventCode', 'parent-child', 'KQL', '2>&1',
            # PowerShell attack techniques (100% chosen rate)
            'invoke-mimikatz', 'hashdump', 'invoke-shellcode', 'invoke-eternalblue',
            # Cmd.exe obfuscation regex patterns (basic threat techniques)
            r'%[A-Za-z0-9_]+:~[0-9]+(,[0-9]+)?%',  # env-var substring access
            r'%[A-Za-z0-9_]+:[^=%%]+=[^%]*%',  # env-var string substitution
            r'![A-Za-z0-9_]+!',  # delayed expansion markers
            r'\bcmd(\.exe)?\s*/V(?::[^ \t/]+)?',  # /V:ON obfuscated variants
            r'\bset\s+[A-Za-z0-9_]+\s*=',  # multiple SET stages
            r'\bcall\s+(set|%[A-Za-z0-9_]+%|![A-Za-z0-9_]+!)',  # CALL invocation
            r'(%[^%]+%){4,}',  # adjacent env-var concatenation
            r'\bfor\s+/?[A-Za-z]*\s+%[A-Za-z]\s+in\s*\(',  # FOR loops
            r'![A-Za-z0-9_]+:~%[A-Za-z],1!',  # FOR-indexed substring extraction
            r'\bfor\s+/L\s+%[A-Za-z]\s+in\s*\([^)]+\)',  # reversal via /L
            r'%[A-Za-z0-9_]+:~-[0-9]+%|%[A-Za-z0-9_]+:~[0-9]+%',  # tail trimming
            r'%[A-Za-z0-9_]+:\*[^!%]+=!%',  # asterisk-based substitution
            r'[^\w](s\^+e\^*t|s\^*e\^+t)[^\w]',  # caret-obfuscated set
            r'[^\w](c\^+a\^*l\^*l|c\^*a\^+l\^*l|c\^*a\^*l\^+l)[^\w]',  # caret-obfuscated call
            r'\^|"',  # caret or quote splitting
            r'%[^%]+%<[^>]*|set\s+[A-Za-z0-9_]+\s*=\s*[^&|>]*\|',  # stdin piping patterns
            # macOS-specific perfect discriminators (100% chosen rate)
            'homebrew', '/users/shared/', 'chmod 777',
            # macOS telemetry and security controls (100% chosen rate)
            'tccd', 'spctl', 'csrutil',
            # Added from non-English word analysis
            'xor',
            # High-performing keywords from analysis (80%+ chosen rate)
            'tcp://', 'CN=', '-ComObject', 'Chcp', 'tostring', 'HKCU', 'System32',
            'Hxxp', 'Cmd', '8080', 'XOR', 'User-Agent', 'sshd', 'Base64',
            # Perfect threat hunting discriminators (>75% in 90+ hunt score range)
            'icacls', 'InteropServices.Marshal', 'selection1:', 'dclist', 'invoke-',
            'tasklist', 'adfind', '-EncodedCommand', 'selection_1:', 'attrib',
            # Low-rejection keywords from analysis (0-2 rejected)
            'System.IO', 'New-Object', 'StreamReader', 'ByteArray', '127.0.0.1', '>1', 'admin$',
            'MpPreference', 'Whoami', 'C$', 'MSBuild', '7z',
            # High-performing non-Windows keywords (>90% chosen rate)
            'auditd', 'systemd', 'xattr', 'EndpointSecurity', 'osquery',
            'zeek', 'dns_query', 'ja3',
            # WMI reconnaissance patterns (high threat hunting value)
            'SELECT * FROM'
        ],
            'good_discriminators': [
                'temp', '==', 'c:\\windows\\', 'Event ID', '.bat', '.ps1',
                'pipe', '::', '[.]', '-->', 'currentversion',
                'Monitor', 'Executable', 'Detection', 'Alert on', 'Hunt for',
                'Hunting', 'Create Detections', 'Search Query', '//',
                'http:', 'hxxp', '->', '.exe', '--',
                '\\\\', 'spawn', '|',
                # PowerShell attack techniques (high chosen rate)
                'mimikatz', 'kerberoast', 'psexec',
                # macOS-specific good discriminators (high chosen rate)
                'mach-o', 'plist',
                # macOS attack vectors and telemetry (60%+ chosen rate)
                'osascript', 'TCC.db',
                # Added from non-English word analysis
                'payload', 'sftp', 'downloader', 'jss',
                # Character pattern discriminators (high correlation analysis)
                '{}', '<>', '[]',
                # Medium-performing keywords from analysis (50%+ chosen rate)
                'win32_', 'Httpd', 'Int64', '/usr/', 'echo', '/tmp/', '/etc/',
                # Additional non-Windows keywords for comprehensive coverage
                'syslog', 'sudo', 'cron', 'LD_PRELOAD', 'launchd',
                'auditlog', 'iam', 'snort', 'proxy', 'http_request', 'anomaly',
                'linux', 'macos', 'cloud', 'aws', 'azure', 'network', 'ssl',
                # Moved from Perfect (didn't meet 90% threshold)
                'codesign', 'cloudtrail', 'guardduty', 's3', 'ec2', 'gcp',
                'suricata', 'netflow', 'beaconing', 'user-agent',
                # Good threat hunting discriminators (≤75% in 90+ hunt score range)
                'process_creation', 'reg add', 'logsource:', 'get-', 'selection:',
                'DeviceProcessEvents', 'hxxps', 'taskkill.exe', 'detection:', 'DeviceFileEvents',
                'child'
            ],
    'intelligence_indicators': [
        # Real threat activity - specific indicators
        'APT', 'threat actor', 'attribution', 'campaign', 'incident',
        'breach', 'compromise', 'malware family', 'IOC', 'indicator',
        'TTP', 'technique', 'observed', 'discovered', 'detected in wild',
        'real-world', 'in the wild', 'in-the-wild', 'active campaign', 'ongoing threat',
        'victim', 'targeted', 'exploited', 'compromised', 'infiltrated',
        
        # Attack lifecycle phases (high-priority additions)
        'intrusion', 'beacon', 'lateral movement', 'persistence', 'reconnaissance',
        'exfiltration', 'command and control', 'c2', 'initial access', 'privilege escalation',
        
        # Specific threat groups
        'FIN', 'TA', 'UNC', 'APT1', 'APT28', 'APT29', 'Lazarus', 'Carbanak',
        'Cozy Bear', 'Fancy Bear', 'Wizard Spider', 'Ryuk', 'Maze',
        
        # Real incidents and attacks
        'ransomware', 'data breach', 'cyber attack', 'espionage',
        'sophisticated attack', 'advanced persistent threat',
        
        # Rare Kerberos attack techniques (future content detection)
        'golden-ticket', 'silver-ticket'
    ],
    'negative_indicators': [
        # Educational/marketing content that should be penalized
        'what is', 'how to', 'guide to', 'tutorial', 'best practices',
        'statistics', 'survey', 'report shows', 'study reveals',
        'learn more', 'read more', 'click here', 'download now',
        'free trial', 'contact us', 'get started', 'sign up',
        'blog post', 'newsletter', 'webinar', 'training',
        'overview', 'introduction', 'basics', 'fundamentals'
    ],
    'lolbas_executables': [
        'certutil.exe', 'cmd.exe', 'schtasks.exe', 'wmic.exe', 'bitsadmin.exe', 'ftp.exe', 'netsh.exe', 'cscript.exe', 'mshta.exe',
        'regsvr32.exe', 'rundll32.exe', 'forfiles.exe', 'explorer.exe', 'ieexec.exe', 'powershell.exe', 'conhost.exe', 'svchost.exe', 'lsass.exe',
        'csrss.exe', 'smss.exe', 'wininit.exe', 'nltest.exe', 'odbcconf.exe', 'scrobj.dll', 'addinutil.exe', 'appinstaller.exe', 'aspnet_compiler.exe',
        'at.exe', 'atbroker.exe', 'bash.exe', 'certoc.exe', 'certreq.exe', 'cipher.exe', 'cmdkey.exe', 'cmdl32.exe', 'cmstp.exe', 'colorcpl.exe',
        'computerdefaults.exe', 'configsecuritypolicy.exe', 'control.exe', 'csc.exe', 'customshellhost.exe', 'datasvcutil.exe',
        'desktopimgdownldr.exe', 'devicecredentialdeployment.exe', 'dfsvc.exe', 'diantz.exe', 'diskshadow.exe', 'dnscmd.exe', 'esentutl.exe',
        'eventvwr.exe', 'expand.exe', 'extexport.exe', 'extrac32.exe', 'findstr.exe', 'finger.exe', 'fltmc.exe', 'gpscript.exe',
        'replace.exe', 'sc.exe', 'print.exe', 'ssh.exe', 'teams.exe', 'rdrleakdiag.exe', 'ipconfig.exe', 'systeminfo.exe',
        'aspnet_com.exe', 'acroreer.exe', 'change.exe', 'configse.exe', 'customshell.exe', 'datasecutil.exe', 'desktopimg.exe',
        'devicescred.exe', 'dism.exe', 'eudcedit.exe', 'export.exe', 'finger.exe', 'flmc.exe', 'fsutil.exe', 'gscript.exe', 'hh.exe', 'imewdbld.exe',
        'ie4uinit.exe', 'inetcpl.exe', 'installutil.exe', 'iscsicpl.exe', 'isc.exe', 'ldifde.exe', 'makecab.exe', 'mavinject.exe',
        'microsoft.workflow.exe', 'mmc.exe', 'mpcmdrun.exe', 'msbuild.exe', 'msconfig.exe', 'msdt.exe', 'msedge.exe', 'ngen.exe',
        'offlinescanner.exe', 'onedrivesta.exe', 'pcalua.exe', 'pcwrun.exe', 'platman.exe', 'pnputil.exe', 'presentationsettings.exe',
        'print.exe', 'printbrm.exe', 'prowlaunch.exe', 'psr.exe', 'query.exe', 'rasautou.exe', 'rdrleakdiag.exe', 'reg.exe', 'regasm.exe', 'regedit.exe',
        'regini.exe', 'register-cim.exe', 'replace.exe', 'reset.exe', 'rpcping.exe', 'runschlp.exe', 'runonce.exe', 'runscripthelper.exe',
        'scriptrunner.exe', 'setres.exe', 'settingsynchost.exe', 'sftp.exe', 'syncappvpublishingserver.exe', 'tar.exe', 'tldinject.exe',
        'tracerpt.exe', 'unregmp2.exe', 'wbc.exe', 'vssadmin.exe', 'wab.exe', 'wbadmin.exe', 'wbemtest.exe', 'wfgen.exe', 'wfp.exe', 'winword.exe',
        'wsreset.exe', 'wuzucht.exe', 'xwizard.exe', 'msedge_proxy.exe', 'msedgewebview2.exe', 'wsl.exe', 'adxpack.dll', 'desk.cpl', 'ieframe.dll',
        'mshtml.dll', 'pcwutil.dll', 'photoviewer.dll', 'setupapi.dll', 'shdocvw.dll', 'shell32.dll', 'shimgvw.dll', 'syssetup.dll', 'url.dll',
        'zipfldr.dll', 'comsvcs.dll', 'acccheckco.dll', 'adplus.exe', 'agentexecu.exe', 'applauncher.exe', 'appcert.exe', 'appvlp.exe', 'bginfo.exe',
        'cdb.exe', 'coregen.exe', 'createdump.exe', 'csi.exe', 'defaultpack.exe', 'devinit.exe', 'devtroubleshoot.exe', 'dnx.exe', 'dotnet.exe',
        'dpubuild.exe', 'dputil.exe', 'dump64.exe', 'dumpmini.exe', 'dxcap.exe', 'ecmangen.exe', 'excel.exe', 'foj.exe', 'fsrmgpu.exe', 'hltrace.exe',
        'microsoft.notes.exe', 'mpiexec.exe', 'msaccess.exe', 'msdeploy.exe', 'msohtmed.exe', 'mspub.exe', 'mses.exe', 'ndsutil.exe', 'ntds.exe',
        'openconsole.exe', 'pstools.exe', 'powerpnt.exe', 'procdump.exe', 'protocolhandler.exe', 'rcsi.exe', 'remote.exe', 'sqldumper.exe',
        'sqlps.exe', 'sqltoolsps.exe', 'squirrel.exe', 'ta.exe', 'teams.exe', 'testwindow.exe', 'tracker.exe', 'update.exe', 'vsdiagnostic.exe',
        'vsixinstaller.exe', 'visio.exe', 'visualuiaver.exe', 'vsixlaunch.exe', 'vsshadow.exe', 'wsgldebugger.exe', 'wfhformat.exe', 'wic.exe',
        'windbg.exe', 'winproj.exe', 'xbootmgr.exe', 'xtoolmgr.exe', 'rdptunnel.exe', 'wslg-agent.exe', 'wstest_console.exe', 'winfile.exe',
        'xsd.exe', 'cl_loadas.exe', 'cl_mute.exe', 'cl_invoca.exe', 'launch-vsd.exe', 'manage-bde.exe', 'pubprn.vbs', 'syncappvpu.exe',
        'utilityfunc.exe', 'winrm.vbs', 'poster.bat'
    ],
}


class ThreatHuntingScorer:
    """Enhanced scoring for threat hunting and malware analysis content."""
    
    @staticmethod
    def score_threat_hunting_content(title: str, content: str) -> Dict[str, Any]:
        """
        Score content for threat hunting quality using Windows malware keywords.
        
        Returns:
            Dict containing:
            - threat_hunting_score: float (0-100)
            - perfect_keyword_matches: List[str]
            - good_keyword_matches: List[str]
            - lolbas_matches: List[str]
            - intelligence_matches: List[str]
            - negative_matches: List[str]
        """
        if not content:
            return {
                'threat_hunting_score': 0.0,
                'perfect_keyword_matches': [],
                'good_keyword_matches': [],
                'lolbas_matches': [],
                'intelligence_matches': [],
                'negative_matches': []
            }
        
        # Clean content for analysis
        clean_content = ContentCleaner.html_to_text(content).lower()
        title_lower = title.lower() if title else ""
        full_text = f"{title_lower} {clean_content}"
        
        # Find keyword matches
        perfect_matches = []
        good_matches = []
        lolbas_matches = []
        intelligence_matches = []
        
        # Check perfect discriminators
        for keyword in WINDOWS_MALWARE_KEYWORDS['perfect_discriminators']:
            if ThreatHuntingScorer._keyword_matches(keyword, full_text):
                perfect_matches.append(keyword)
        
        # Check good discriminators
        for keyword in WINDOWS_MALWARE_KEYWORDS['good_discriminators']:
            if ThreatHuntingScorer._keyword_matches(keyword, full_text):
                good_matches.append(keyword)
        
        # Check LOLBAS executables
        for executable in WINDOWS_MALWARE_KEYWORDS['lolbas_executables']:
            if ThreatHuntingScorer._keyword_matches(executable, full_text):
                lolbas_matches.append(executable)
        
        # Check intelligence indicators
        for indicator in WINDOWS_MALWARE_KEYWORDS['intelligence_indicators']:
            if ThreatHuntingScorer._keyword_matches(indicator, full_text):
                intelligence_matches.append(indicator)
        
        # Check negative indicators (penalize educational/marketing content)
        negative_matches = []
        for negative in WINDOWS_MALWARE_KEYWORDS['negative_indicators']:
            if ThreatHuntingScorer._keyword_matches(negative, full_text):
                negative_matches.append(negative)
        
        # Calculate scores using logarithmic bucket system with diminishing returns
        import math
        
        # Perfect Discriminators: 75 points max (dominant weight for technical depth)
        perfect_score = min(35 * math.log(len(perfect_matches) + 1), 75.0)
        
        # LOLBAS Executables: 10 points max (practical attack techniques)
        lolbas_score = min(5 * math.log(len(lolbas_matches) + 1), 10.0)
        
        # Intelligence Indicators: 10 points max (core threat intelligence value)
        intelligence_score = min(4 * math.log(len(intelligence_matches) + 1), 10.0)
        
        # Good Discriminators: 5 points max (supporting technical content)
        good_score = min(2.5 * math.log(len(good_matches) + 1), 5.0)
        
        # Negative Penalties: -10 points max (educational/marketing content penalty)
        negative_penalty = min(3 * math.log(len(negative_matches) + 1), 10.0)

        # Calculate final threat hunting score (0-100 range)
        threat_hunting_score = max(0.0, min(100.0, perfect_score + good_score + lolbas_score + intelligence_score - negative_penalty))

        return {
            'threat_hunting_score': round(threat_hunting_score, 1),
            'perfect_keyword_matches': perfect_matches,
            'good_keyword_matches': good_matches,
            'lolbas_matches': lolbas_matches,
            'intelligence_matches': intelligence_matches,
            'negative_matches': negative_matches
        }
    
    @staticmethod
    def _keyword_matches(keyword: str, text: str) -> bool:
        """
        Check if keyword matches in text using word boundaries or regex patterns.
        
        Args:
            keyword: Keyword to search for (can be regex pattern)
            text: Text to search in
            
        Returns:
            True if keyword is found with proper word boundaries or regex match
        """
        # Regex patterns for cmd.exe obfuscation techniques
        regex_patterns = [
            r'%[A-Za-z0-9_]+:~[0-9]+(,[0-9]+)?%',  # env-var substring access
            r'%[A-Za-z0-9_]+:[^=%%]+=[^%]*%',  # env-var string substitution
            r'![A-Za-z0-9_]+!',  # delayed expansion markers
            r'\bcmd(\.exe)?\s*/V(?::[^ \t/]+)?',  # /V:ON obfuscated variants
            r'\bset\s+[A-Za-z0-9_]+\s*=',  # multiple SET stages
            r'\bcall\s+(set|%[A-Za-z0-9_]+%|![A-Za-z0-9_]+!)',  # CALL invocation
            r'(%[^%]+%){4,}',  # adjacent env-var concatenation
            r'\bfor\s+/?[A-Za-z]*\s+%[A-Za-z]\s+in\s*\(',  # FOR loops
            r'![A-Za-z0-9_]+:~%[A-Za-z],1!',  # FOR-indexed substring extraction
            r'\bfor\s+/L\s+%[A-Za-z]\s+in\s*\([^)]+\)',  # reversal via /L
            r'%[A-Za-z0-9_]+:~-[0-9]+%|%[A-Za-z0-9_]+:~[0-9]+%',  # tail trimming
            r'%[A-Za-z0-9_]+:\*[^!%]+=!%',  # asterisk-based substitution
            r'[^\w](s\^+e\^*t|s\^*e\^+t)[^\w]',  # caret-obfuscated set
            r'[^\w](c\^+a\^*l\^*l|c\^*a\^+l\^*l|c\^*a\^*l\^+l)[^\w]',  # caret-obfuscated call
            r'[^\w]([a-z]\^+[a-z](\^+[a-z])*)[^\w]',  # caret-obfuscated commands (any length)
            r'%[^%]+%<[^>]*|set\s+[A-Za-z0-9_]+\s*=\s*[^&|>]*\|'  # stdin piping patterns
        ]
        
        # Check if keyword is a regex pattern
        if keyword in regex_patterns:
            return bool(re.search(keyword, text, re.IGNORECASE))
        
        # Get regex pattern for matching
        pattern = ThreatHuntingScorer._build_keyword_pattern(keyword)
        
        return bool(re.search(pattern, text, re.IGNORECASE))
    
    @staticmethod
    def _build_keyword_pattern(keyword: str) -> str:
        """
        Build regex pattern for keyword matching.
        Shared logic used by both scoring and highlighting.
        
        Args:
            keyword: Keyword to build pattern for
            
        Returns:
            Regex pattern string
        """
        # Escape special regex characters for literal matching
        escaped_keyword = re.escape(keyword)
        
        # For certain keywords, allow partial matches (like "hunting" in "threat hunting")
        partial_match_keywords = ['hunting', 'detection', 'monitor', 'alert', 'executable', 'parent-child', 'defender query']
        
        # For wildcard keywords, use prefix matching
        wildcard_keywords = ['spawn']
        
        # For symbol keywords and path prefixes, don't use word boundaries
        symbol_keywords = ['==', '!=', '<=', '>=', '::', '-->', '->', '//', '--', '\\', '|', 'C:\\', 'D:\\']
        
        if keyword.lower() in partial_match_keywords:
            # Allow partial matches for these keywords
            return escaped_keyword
        elif keyword.lower() in wildcard_keywords:
            # Allow wildcard matching (e.g., "spawn" matches "spawns", "spawning", "spawned")
            return escaped_keyword + r'\w*'
        elif keyword in symbol_keywords:
            # For symbols, don't use word boundaries
            return escaped_keyword
        elif keyword.startswith('-') or keyword.endswith('-'):
            # For keywords with leading/trailing hyphens, use letter boundaries instead of word boundaries
            return r"(?<![a-zA-Z])" + escaped_keyword + r"(?![a-zA-Z])"
        elif keyword.endswith('.exe'):
            # For .exe executables, match both with and without .exe extension
            base_name = keyword[:-4]  # Remove .exe
            return r'\b' + re.escape(base_name) + r'(\.exe)?\b'
        elif keyword.endswith('.dll'):
            # For .dll files, match both with and without .dll extension
            base_name = keyword[:-4]  # Remove .dll
            return r'\b' + re.escape(base_name) + r'(\.dll)?\b'
        elif ' ' in keyword:
            # For multi-word phrases, ensure word boundaries at start and end
            # but allow flexible matching in the middle
            return r'\b' + escaped_keyword + r'\b'
        else:
            # Use word boundaries for other keywords
            return r'\b' + escaped_keyword + r'\b'


class ContentExtractor:
    """Extract content and metadata from HTML."""
    
    def __init__(self):
        self.soup = None
    
    def extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try title tag first
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                return title_tag.string.strip()
            
            # Try h1 tag
            h1_tag = soup.find('h1')
            if h1_tag:
                return h1_tag.get_text(strip=True)
            
            # Try meta title
            meta_title = soup.find('meta', {'property': 'og:title'})
            if meta_title and meta_title.get('content'):
                return meta_title.get('content').strip()
            
            return ""
        except Exception:
            return ""
    
    def extract_meta_description(self, html: str) -> str:
        """Extract meta description from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try meta description
            meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                return meta_desc.get('content').strip()
            
            # Try OpenGraph description
            og_desc = soup.find('meta', {'property': 'og:description'})
            if og_desc and og_desc.get('content'):
                return og_desc.get('content').strip()
            
            return ""
        except Exception:
            return ""
    
    def extract_keywords(self, html: str) -> List[str]:
        """Extract keywords from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try meta keywords
            meta_keywords = soup.find('meta', {'name': 'keywords'})
            if meta_keywords and meta_keywords.get('content'):
                keywords = [k.strip() for k in meta_keywords.get('content').split(',')]
                return [k for k in keywords if k]
            
            return []
        except Exception:
            return []
    
    def extract_author(self, html: str) -> str:
        """Extract author from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try meta author
            meta_author = soup.find('meta', {'name': 'author'})
            if meta_author and meta_author.get('content'):
                return meta_author.get('content').strip()
            
            # Try OpenGraph author
            og_author = soup.find('meta', {'property': 'article:author'})
            if og_author and og_author.get('content'):
                return og_author.get('content').strip()
            
            return ""
        except Exception:
            return ""
    
    def extract_published_date(self, html: str) -> str:
        """Extract published date from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try meta published time (both property and name attributes)
            meta_date = soup.find('meta', {'property': 'article:published_time'}) or soup.find('meta', {'name': 'article:published_time'})
            if meta_date and meta_date.get('content'):
                return meta_date.get('content').strip()
            
            # Try time tag
            time_tag = soup.find('time')
            if time_tag and time_tag.get('datetime'):
                return time_tag.get('datetime').strip()
            
            return ""
        except Exception:
            return ""
    
    def extract_canonical_url(self, html: str) -> str:
        """Extract canonical URL from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Try canonical link
            canonical = soup.find('link', {'rel': 'canonical'})
            if canonical and canonical.get('href'):
                return canonical.get('href').strip()
            
            return ""
        except Exception:
            return ""
    
    def extract_all_metadata(self, html: str) -> Dict[str, Any]:
        """Extract all metadata from HTML."""
        return {
            'title': self.extract_title(html),
            'description': self.extract_meta_description(html),
            'keywords': self.extract_keywords(html),
            'author': self.extract_author(html),
            'published_date': self.extract_published_date(html),
            'canonical_url': self.extract_canonical_url(html)
        }


class TextNormalizer:
    """Normalize text content."""
    
    def __init__(self):
        self.unicode_map = {
            '“': '"', '"': '"', ''': "'", ''': "'",
            '–': '-', '—': '-', '…': '...',
            '©': '(c)', '®': '(r)', '™': '(tm)'
        }
    
    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        if not text:
            return ""
        
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters."""
        if not text:
            return ""
        
        # Replace common Unicode characters
        for unicode_char, ascii_char in self.unicode_map.items():
            text = text.replace(unicode_char, ascii_char)
        
        # Additional Unicode normalization for accented characters
        import unicodedata
        # Normalize to NFD (decomposed form) and remove combining characters
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        
        return text
    
    def normalize_case(self, text: str) -> str:
        """Normalize text case."""
        if not text:
            return ""
        
        # Convert to lowercase
        return text.lower()
    
    def remove_special_characters(self, text: str) -> str:
        """Remove special characters from text."""
        if not text:
            return ""
        
        # Remove special characters but keep alphanumeric, spaces, and basic punctuation
        # Remove @#$%^&*()! and other special chars, keep only letters, numbers, spaces, and basic punctuation
        text = re.sub(r'[^\w\s\.\,\;\:\?]', ' ', text)
        return self.normalize_whitespace(text)
    
    def normalize_text(self, text: str) -> str:
        """Comprehensive text normalization."""
        if not text:
            return ""
        
        # Apply all normalization steps in correct order
        text = self.normalize_unicode(text)
        text = self.remove_special_characters(text)
        text = self.normalize_whitespace(text)
        text = self.normalize_case(text)
        
        return text
    
