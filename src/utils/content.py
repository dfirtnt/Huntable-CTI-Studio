"""Content processing utilities for threat intelligence articles."""

import re
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# Windows malware/threat hunting keywords from analysis
WINDOWS_MALWARE_KEYWORDS = {
    # Perfect discriminators (100% Chosen, 0% others)
    'perfect_discriminators': [
        'rundll32', 'comspec', 'msiexec', 'wmic', 'iex', 'findstr',
        'hklm', 'appdata', 'programdata', 'powershell.exe', 'wbem',
        'EventID', '.lnk', 'D:\\', '.iso', '<Command>', 'MZ',
        'svchost', '-accepteula', 'lsass.exe', 'WINDIR', 'wintmp',
        '\\temp\\', '\\pipe\\', '%WINDIR%', '%wintmp%'
    ],
    # Good discriminators (high Chosen ratio)
    'good_discriminators': [
        'temp', '==', 'c:\\windows\\', 'Event ID', '.bat', '.ps1',
        'pipe', '::', '[.]', '-->', 'currentversion', 'EventCode'
    ],
    # LOLBAS (Living Off the Land Binaries and Scripts) - 68 Chosen, 2 Rejected
    'lolbas_executables': [
        'AddinUtil.exe', 'AppInstaller.exe', 'Aspnet_Compiler.exe', 'At.exe', 'Atbroker.exe',
        'Bash.exe', 'Bitsadmin.exe', 'CertOC.exe', 'CertReq.exe', 'Certutil.exe', 'Cipher.exe',
        'Cmd.exe', 'Cmdkey.exe', 'cmdl32.exe', 'Cmstp.exe', 'Colorcpl.exe', 'ComputerDefaults.exe',
        'ConfigSecurityPolicy.exe', 'Conhost.exe', 'Control.exe', 'Csc.exe', 'Cscript.exe',
        'CustomShellHost.exe', 'DataSvcUtil.exe', 'Desktopimgdownldr.exe', 'DeviceCredentialDeployment.exe',
        'Dfsvc.exe', 'Diantz.exe', 'Diskshadow.exe', 'Dnscmd.exe', 'Esentutl.exe', 'Eventvwr.exe',
        'Expand.exe', 'Explorer.exe', 'Extexport.exe', 'Extrac32.exe', 'Findstr.exe', 'Finger.exe',
        'fltMC.exe', 'Forfiles.exe', 'Fsutil.exe', 'Ftp.exe', 'Gpscript.exe', 'Hh.exe',
        'IMEWDBLD.exe', 'Ie4uinit.exe', 'iediagcmd.exe', 'Ieexec.exe', 'Ilasm.exe', 'Infdefaultinstall.exe',
        'Installutil.exe', 'Jsc.exe', 'Ldifde.exe', 'Makecab.exe', 'Mavinject.exe',
        'Microsoft.Workflow.Compiler.exe', 'Mmc.exe', 'MpCmdRun.exe', 'Msbuild.exe', 'Msconfig.exe',
        'Msdt.exe', 'Msedge.exe', 'Mshta.exe', 'Msiexec.exe', 'Netsh.exe', 'Ngen.exe',
        'Odbcconf.exe', 'OfflineScannerShell.exe', 'OneDriveStandaloneUpdater.exe', 'Pcalua.exe',
        'Pcwrun.exe', 'Pktmon.exe', 'Pnputil.exe', 'Presentationhost.exe', 'Print.exe',
        'PrintBrm.exe', 'Provlaunch.exe', 'Psr.exe', 'Rasautou.exe', 'rdrleakdiag.exe',
        'Reg.exe', 'Regasm.exe', 'Regedit.exe', 'Regini.exe', 'Register-cimprovider.exe',
        'Regsvcs.exe', 'Regsvr32.exe', 'Replace.exe', 'Rpcping.exe', 'Rundll32.exe',
        'Runexehelper.exe', 'Runonce.exe', 'Runscripthelper.exe', 'Sc.exe', 'Schtasks.exe',
        'Scriptrunner.exe', 'Setres.exe', 'SettingSyncHost.exe', 'Sftp.exe', 'ssh.exe',
        'Stordiag.exe', 'SyncAppvPublishingServer.exe', 'Tar.exe', 'Ttdinject.exe', 'Tttracer.exe',
        'Unregmp2.exe', 'vbc.exe', 'Verclsid.exe', 'Wab.exe', 'wbadmin.exe', 'wbemtest.exe',
        'winget.exe', 'Wlrmdr.exe', 'Wmic.exe', 'WorkFolders.exe', 'Wscript.exe', 'Wsreset.exe',
        'wuauclt.exe', 'Xwizard.exe', 'msedge_proxy.exe', 'msedgewebview2.exe', 'wt.exe',
        'AccCheckConsole.exe', 'adplus.exe', 'AgentExecutor.exe', 'AppCert.exe', 'Appvlp.exe',
        'Bginfo.exe', 'Cdb.exe', 'coregen.exe', 'Createdump.exe', 'csi.exe', 'DefaultPack.EXE',
        'Devinit.exe', 'Devtoolslauncher.exe', 'dnx.exe', 'Dotnet.exe', 'dsdbutil.exe',
        'dtutil.exe', 'Dump64.exe', 'DumpMinitool.exe', 'Dxcap.exe', 'ECMangen.exe',
        'Excel.exe', 'Fsi.exe', 'FsiAnyCpu.exe', 'Mftrace.exe', 'Microsoft.NodejsTools.PressAnyKey.exe',
        'MSAccess.exe', 'Msdeploy.exe', 'MsoHtmEd.exe', 'Mspub.exe', 'msxsl.exe', 'ntdsutil.exe',
        'OpenConsole.exe', 'Powerpnt.exe', 'Procdump.exe', 'ProtocolHandler.exe', 'rcsi.exe',
        'Remote.exe', 'Sqldumper.exe', 'Sqlps.exe', 'SQLToolsPS.exe', 'Squirrel.exe', 'te.exe',
        'Teams.exe', 'TestWindowRemoteAgent.exe', 'Tracker.exe', 'Update.exe', 'VSDiagnostics.exe',
        'VSIISExeLauncher.exe', 'Visio.exe', 'VisualUiaVerifyNative.exe', 'VSLaunchBrowser.exe',
        'Vshadow.exe', 'vsjitdebugger.exe', 'WFMFormat.exe', 'Wfc.exe', 'WinProj.exe',
        'Winword.exe', 'Wsl.exe', 'XBootMgrSleep.exe', 'devtunnel.exe', 'vsls-agent.exe',
        'vstest.console.exe', 'winfile.exe', 'xsd.exe'
    ],
    # Threat hunting terminology and concepts
    'threat_hunting_terms': [
        'lolbas', 'lolbins', 'RMM'
    ]
}


class ContentCleaner:
    """Utilities for cleaning and normalizing content."""
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        if not text:
            return ""
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    @staticmethod
    def clean_html(html_content: str) -> str:
        """Clean HTML content while preserving structure."""
        if not html_content:
            return ""
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        return text
    
    @staticmethod
    def html_to_text(html_content: str) -> str:
        """Convert HTML to plain text."""
        if not html_content:
            return ""
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        return text
    
    @staticmethod
    def extract_summary(content: str, max_length: int = 300) -> str:
        """Extract a summary from content."""
        if not content:
            return ""
        
        # Clean the content
        clean_content = ContentCleaner.html_to_text(content)
        
        # Take first max_length characters
        if len(clean_content) <= max_length:
            return clean_content
        
        # Try to break at sentence boundary
        summary = clean_content[:max_length]
        last_period = summary.rfind('.')
        last_exclamation = summary.rfind('!')
        last_question = summary.rfind('?')
        
        # Find the last sentence ending
        last_sentence = max(last_period, last_exclamation, last_question)
        
        if last_sentence > max_length * 0.7:  # If we have a good sentence break
            summary = summary[:last_sentence + 1]
        
        return summary.strip()
    
    @staticmethod
    def calculate_content_hash(title: str, content: str) -> str:
        """Calculate SHA256 hash of title and content."""
        combined = f"{title}\n{content}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()


class DateExtractor:
    """Utilities for extracting and parsing dates."""
    
    # Common date patterns
    DATE_PATTERNS = [
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
        r'(\d{2}-\d{2}-\d{4})',  # MM-DD-YYYY
        r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})',  # DD MMM YYYY
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',  # ISO format
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)',  # ISO format with Z
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})',  # ISO format with timezone
    ]
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        try:
            # Try parsing with feedparser's date parser
            import feedparser
            parsed = feedparser._parse_date(date_str)
            if parsed:
                return datetime(*parsed[:6])
        except Exception:
            pass
        
        # Try common formats
        for pattern in DateExtractor.DATE_PATTERNS:
            match = re.search(pattern, date_str)
            if match:
                try:
                    date_part = match.group(1)
                    # Try different parsing approaches
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d %b %Y', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            return datetime.strptime(date_part, fmt)
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    @staticmethod
    def extract_date_from_url(url: str) -> Optional[datetime]:
        """Extract date from URL patterns."""
        if not url:
            return None
        
        # Common URL date patterns
        url_patterns = [
            r'/(\d{4})/(\d{2})/(\d{2})/',  # /YYYY/MM/DD/
            r'/(\d{4})-(\d{2})-(\d{2})/',  # /YYYY-MM-DD/
            r'(\d{4})_(\d{2})_(\d{2})',    # YYYY_MM_DD
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year, month, day = match.groups()
                    return datetime(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue
        
        return None


class MetadataExtractor:
    """Utilities for extracting metadata from HTML."""
    
    @staticmethod
    def extract_authors(soup: BeautifulSoup) -> List[str]:
        """Extract authors from HTML."""
        authors = []
        
        # Common author selectors
        author_selectors = [
            '.author', '.byline', '.author-name', '.writer',
            '[rel="author"]', '.post-author', '.entry-author',
            'meta[name="author"]', 'meta[property="article:author"]'
        ]
        
        for selector in author_selectors:
            elements = soup.select(selector)
            for element in elements:
                if element.name == 'meta':
                    content = element.get('content', '')
                else:
                    content = element.get_text()
                
                if content:
                    author = ContentCleaner.normalize_whitespace(content)
                    if author and author not in authors:
                        authors.append(author)
        
        return authors
    
    @staticmethod
    def extract_tags(soup: BeautifulSoup) -> List[str]:
        """Extract tags/categories from HTML."""
        tags = []
        
        # Common tag selectors
        tag_selectors = [
            '.tags', '.categories', '.tag', '.category',
            '.post-tags', '.entry-tags', '.article-tags'
        ]
        
        for selector in tag_selectors:
            elements = soup.select(selector)
            for element in elements:
                links = element.find_all('a')
                for link in links:
                    tag = ContentCleaner.normalize_whitespace(link.get_text())
                    if tag and tag not in tags:
                        tags.append(tag)
        
        return tags
    
    @staticmethod
    def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL from HTML."""
        canonical = soup.find('link', rel='canonical')
        if canonical:
            return canonical.get('href')
        
        # Try Open Graph URL
        og_url = soup.find('meta', property='og:url')
        if og_url:
            return og_url.get('content')
        
        return None
    
    @staticmethod
    def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract meta tags from HTML."""
        meta_data = {}
        
        meta_tags = soup.find_all('meta')
        for tag in meta_tags:
            name = tag.get('name') or tag.get('property')
            content = tag.get('content')
            
            if name and content:
                meta_data[name] = content
        
        return meta_data
    
    @staticmethod
    def extract_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Open Graph data from HTML."""
        og_data = {}
        
        og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
        for tag in og_tags:
            property_name = tag.get('property', '')
            content = tag.get('content', '')
            
            if property_name and content:
                og_data[property_name] = content
        
        return og_data


class QualityScorer:
    """Utilities for scoring article quality."""
    
    @staticmethod
    def score_article(title: str, content: str, metadata: Dict[str, Any]) -> float:
        """Score article quality based on various factors."""
        score = 50.0  # Base score
        
        try:
            # Title quality (0-20 points)
            if title:
                title_length = len(title.strip())
                if 10 <= title_length <= 100:
                    score += 10
                elif 5 <= title_length <= 150:
                    score += 5
                
                # Check for common spam indicators
                spam_indicators = ['click here', 'buy now', 'limited time', 'act now']
                if not any(indicator in title.lower() for indicator in spam_indicators):
                    score += 10
            
            # Content quality (0-30 points)
            if content:
                content_length = len(ContentCleaner.html_to_text(content))
                if content_length >= 500:
                    score += 15
                elif content_length >= 200:
                    score += 10
                elif content_length >= 100:
                    score += 5
                
                # Check for structured content
                if '<h' in content or '<p>' in content:
                    score += 10
                
                # Check for links (but not too many)
                link_count = content.count('<a href')
                if 1 <= link_count <= 10:
                    score += 5
            
            # Metadata quality (0-20 points)
            if metadata:
                # Check for author information
                if metadata.get('authors'):
                    score += 10
                
                # Check for tags/categories
                if metadata.get('tags'):
                    score += 5
                
                # Check for publication date
                if metadata.get('published_at'):
                    score += 5
            
            # Cap score at 100
            score = min(score, 100.0)
            
        except Exception as e:
            logger.warning(f"Error scoring article: {e}")
            score = 50.0  # Default score on error
        
        return round(score, 1)


def validate_content(title: str, content: str, url: str) -> List[str]:
    """Validate content and return list of issues."""
    issues = []
    
    try:
        # Title validation
        if not title or len(title.strip()) < 5:
            issues.append("Title too short or missing")
        elif len(title.strip()) > 200:
            issues.append("Title too long")
        
        # Content validation
        if not content or len(content.strip()) < 50:
            issues.append("Content too short or missing")
        elif len(content.strip()) > 50000:
            issues.append("Content too long")
        
        # Check for binary/corrupted content
        if _is_binary_content(content):
            issues.append("Content appears to be binary/corrupted data")
        
        # URL validation
        if not url or not url.startswith(('http://', 'https://')):
            issues.append("Invalid URL format")
        
        # Check for obvious spam indicators
        spam_indicators = ['click here', 'buy now', 'limited time', 'act now', 'make money fast']
        text_content = ContentCleaner.html_to_text(content).lower()
        if any(indicator in text_content for indicator in spam_indicators):
            issues.append("Contains spam indicators")
        
        # Check for excessive links
        link_count = content.count('<a href')
        if link_count > 20:
            issues.append("Too many links")
        
    except Exception as e:
        logger.warning(f"Error validating content: {e}")
        issues.append("Validation error")
    
    return issues


def _is_binary_content(content: str) -> bool:
    """Check if content appears to be binary/corrupted data."""
    if not content:
        return False
    
    # Check for high ratio of non-printable characters
    non_printable_count = sum(1 for c in content if not c.isprintable() and not c.isspace())
    total_chars = len(content)
    
    if total_chars > 0:
        non_printable_ratio = non_printable_count / total_chars
        if non_printable_ratio > 0.1:  # More than 10% non-printable
            return True
    
    # Check for common binary patterns
    binary_patterns = [
        b'\x00', b'\xff', b'\xfe', b'\xfd', b'\xfc',  # Common binary bytes
        b'\x1f\x8b',  # Gzip header
        b'PK\x03\x04',  # ZIP header
        b'\x89PNG',  # PNG header
        b'GIF8',  # GIF header
        b'\xff\xd8\xff',  # JPEG header
    ]
    
    try:
        content_bytes = content.encode('utf-8', errors='ignore')
        for pattern in binary_patterns:
            if pattern in content_bytes:
                return True
    except Exception:
        pass
    
    # Check for excessive unicode replacement characters
    if content.count('�') > len(content) * 0.05:  # More than 5% replacement chars
        return True
    
    return False


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
            - keyword_density: float
            - technical_depth_score: float
        """
        if not content:
            return {
                'threat_hunting_score': 0.0,
                'perfect_keyword_matches': [],
                'good_keyword_matches': [],
                'keyword_density': 0.0,
                'technical_depth_score': 0.0
            }
        
        # Clean content for analysis
        clean_content = ContentCleaner.html_to_text(content).lower()
        title_lower = title.lower() if title else ""
        full_text = f"{title_lower} {clean_content}"
        
        # Find keyword matches
        perfect_matches = []
        good_matches = []
        lolbas_matches = []
        threat_hunting_matches = []
        
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
        
        # Check threat hunting terms
        for term in WINDOWS_MALWARE_KEYWORDS['threat_hunting_terms']:
            if ThreatHuntingScorer._keyword_matches(term, full_text):
                threat_hunting_matches.append(term)
        
        # Calculate scores
        perfect_score = len(perfect_matches) * 15  # 15 points per perfect keyword
        good_score = len(good_matches) * 8         # 8 points per good keyword
        lolbas_score = len(lolbas_matches) * 12    # 12 points per LOLBAS executable
        threat_hunting_score = len(threat_hunting_matches) * 10  # 10 points per threat hunting term
        
        # Technical depth indicators
        technical_depth_score = ThreatHuntingScorer._calculate_technical_depth(full_text)
        
        # Keyword density (percentage of content containing technical keywords)
        total_keywords = len(perfect_matches) + len(good_matches) + len(lolbas_matches) + len(threat_hunting_matches)
        keyword_density = (total_keywords / max(len(full_text.split()), 1)) * 1000  # per 1000 words
        
        # Calculate final threat hunting score
        threat_hunting_score = min(perfect_score + good_score + lolbas_score + threat_hunting_score + technical_depth_score, 100.0)
        
        return {
            'threat_hunting_score': round(threat_hunting_score, 1),
            'perfect_keyword_matches': perfect_matches,
            'good_keyword_matches': good_matches,
            'lolbas_matches': lolbas_matches,
            'threat_hunting_matches': threat_hunting_matches,
            'keyword_density': round(keyword_density, 2),
            'technical_depth_score': round(technical_depth_score, 1)
        }
    
    @staticmethod
    def _keyword_matches(keyword: str, text: str) -> bool:
        """Check if a keyword matches in the text with proper regex handling."""
        try:
            # Handle special characters in keywords
            if keyword in ['[.]', '::', '==', '-accepteula', '-->']:
                pattern = re.escape(keyword)
            elif keyword in ['c:\\windows\\', 'D:\\']:
                pattern = re.escape(keyword)
            elif keyword == '<Command>':
                pattern = r'<command>'
            elif keyword == 'Event ID':
                pattern = r'event\s+id'
            elif keyword == 'EventID':
                pattern = r'eventid'
            elif keyword == 'lsass.exe':
                pattern = r'lsass\.exe'
            elif keyword == 'powershell.exe':
                pattern = r'powershell\.exe'
            # Handle LOLBAS executables (case-insensitive, word boundaries)
            elif keyword.endswith('.exe'):
                # Remove .exe extension for matching
                base_name = keyword[:-4]
                pattern = r'\b' + re.escape(base_name) + r'\.exe\b'
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
            
            return bool(re.search(pattern, text, re.IGNORECASE))
        except Exception as e:
            logger.warning(f"Error matching keyword '{keyword}': {e}")
            return False
    
    @staticmethod
    def _calculate_technical_depth(text: str) -> float:
        """Calculate technical depth score based on various indicators."""
        score = 0.0
        
        # Check for technical patterns
        technical_patterns = [
            (r'cve-\d{4}-\d+', 5),           # CVE references
            (r'0x[0-9a-fA-F]+', 3),          # Hex values
            (r'\\[a-zA-Z0-9_]+\\', 2),        # Registry paths
            (r'[A-Z]:\\[\\\w\s]+', 2),       # Windows paths
            (r'powershell|cmd\.exe|cmd', 3),  # Command shells
            (r'\.exe|\.dll|\.sys', 2),        # Executable files
            (r'http[s]?://[^\s]+', 1),        # URLs
            (r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', 2),  # IP addresses
            (r'[a-fA-F0-9]{32,}', 3),         # MD5 hashes
            (r'[a-fA-F0-9]{64,}', 4),         # SHA256 hashes
        ]
        
        for pattern, points in technical_patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            score += min(matches * points, 20)  # Cap at 20 points per pattern
        
        # Check for code blocks or technical formatting
        if re.search(r'```|`.*`|\[.*\]|\(.*\)', text):
            score += 5
        
        # Check for technical terms
        technical_terms = [
            'malware', 'ransomware', 'trojan', 'backdoor', 'rootkit',
            'exploit', 'vulnerability', 'payload', 'shellcode', 'injection',
            'persistence', 'lateral movement', 'privilege escalation',
            'command and control', 'c2', 'beacon', 'dropper', 'loader'
        ]
        
        term_matches = sum(1 for term in technical_terms if term in text.lower())
        score += min(term_matches * 2, 15)  # Cap at 15 points
        
        return min(score, 30.0)  # Cap technical depth at 30 points
