"""Threat Hunting Technique Detection and Analysis.

This module identifies specific, actionable techniques that security teams can hunt for
in their environments, focusing on detectable patterns rather than MITRE ATT&CK taxonomy.
"""

import re
import logging
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class HuntingTechnique:
    """Represents a huntable technique found in content."""
    technique_name: str
    category: str
    confidence: float
    context: str
    matched_text: str
    hunting_guidance: str
    position: Tuple[int, int]  # (start, end) character positions
    relevance_score: float  # New field for relevance scoring


@dataclass
class ThreatHuntingAnalysis:
    """Complete threat hunting analysis results for an article."""
    article_id: int
    total_techniques: int
    techniques_by_category: Dict[str, List[HuntingTechnique]]
    threat_actors: List[str]
    malware_families: List[str]
    attack_vectors: List[str]
    overall_confidence: float
    hunting_priority: str  # High, Medium, Low
    content_quality_score: float  # New field for content quality


class ThreatHuntingDetector:
    """
    Detects huntable techniques from threat intelligence content.
    
    Focuses on specific, actionable patterns that security teams can use
    for threat hunting in their environments.
    """
    
    def __init__(self):
        """Initialize the threat hunting detector."""
        self.technique_patterns = self._build_hunting_patterns()
        self.threat_actor_patterns = self._build_threat_actor_patterns()
        self.malware_patterns = self._build_malware_patterns()
        self.attack_vector_patterns = self._build_attack_vector_patterns()
        
        # Content quality indicators
        self.quality_indicators = self._build_quality_indicators()
        
        # Noise reduction patterns (common words that shouldn't trigger alerts)
        self.noise_patterns = self._build_noise_patterns()
    
    def _build_noise_patterns(self) -> List[str]:
        """Build patterns for common noise words that shouldn't trigger alerts."""
        return [
            r'\b(blog|post|article|report|analysis|study|research)\b',
            r'\b(company|organization|team|group|department)\b',
            r'\b(announcement|news|update|release|version)\b',
            r'\b(conference|event|meeting|presentation|webinar)\b',
            r'\b(partner|customer|client|user|community)\b',
            r'\b(website|page|link|url|address)\b',
            r'\b(contact|email|phone|support|help)\b'
        ]
    
    def _build_quality_indicators(self) -> Dict[str, List[str]]:
        """Build indicators for content quality assessment."""
        return {
            "technical_depth": [
                "command line", "process execution", "registry key", "file path",
                "network connection", "authentication", "privilege escalation",
                "lateral movement", "persistence", "data exfiltration"
            ],
            "actionable_indicators": [
                "ioc", "indicator of compromise", "hash", "sha256", "md5",
                "ip address", "domain", "url", "email", "filename",
                "registry path", "process name", "service name"
            ],
            "threat_context": [
                "campaign", "threat actor", "malware family", "attack vector",
                "vulnerability", "exploit", "zero-day", "cve-", "mitre att&ck"
            ],
            "detection_logic": [
                "sigma rule", "yara rule", "detection rule", "hunting query",
                "splunk query", "elasticsearch query", "kql", "spl"
            ]
        }
    
    def _build_hunting_patterns(self) -> Dict[str, List[Dict]]:
        """Build patterns for huntable techniques organized by category."""
        return {
            "Credential Access": [
                {
                    "name": "Password Spraying",
                    "patterns": [
                        r'\b(Password\s+Spray|Password\s+Spraying|Credential\s+Spray)\b',
                        r'\b(Brute\s+Force.*Password|Password.*Brute\s+Force)\b',
                        r'\b(Mass\s+Login.*Attempt|Bulk\s+Authentication)\b',
                        # More specific patterns
                        r'\b(attempted\s+\d+\s+logins?\s+across\s+\d+\s+accounts?)\b',
                        r'\b(failed\s+authentication\s+attempts?\s+from\s+multiple\s+users?)\b'
                    ],
                    "hunting_guidance": "Monitor for multiple failed login attempts across multiple accounts, look for authentication logs with high failure rates",
                    "relevance_threshold": 0.7
                },
                {
                    "name": "Credential Dumping",
                    "patterns": [
                        r'\b(Credential\s+Dump|Password\s+Dump|Hash\s+Dump)\b',
                        r'\b(Mimikatz|LSASS|Memory\s+Dump.*Credential)\b',
                        r'\b(Procdump.*LSASS|WDigest|Kerberos\s+Credential)\b',
                        # Specific tools and techniques
                        r'\b(mimikatz\.exe|procdump\.exe|wdigest\.dll)\b',
                        r'\b(lsass\.exe\s+memory\s+dump)\b',
                        r'\b(sekurlsa::logonpasswords|sekurlsa::wdigest)\b'
                    ],
                    "hunting_guidance": "Look for LSASS memory dumps, unusual process creation, WDigest registry modifications, Kerberos ticket requests",
                    "relevance_threshold": 0.8
                }
            ],
            
            "Lateral Movement": [
                {
                    "name": "RDP Exploitation",
                    "patterns": [
                        r'\b(RDP.*Exploit|Remote\s+Desktop.*Attack)\b',
                        r'\b(RDP.*Brute\s+Force|RDP.*Password\s+Spray)\b',
                        r'\b(RDP.*Lateral|RDP.*Movement)\b',
                        # Specific RDP patterns
                        r'\b(tscon\.exe|mstsc\.exe|rdp\s+connection)\b',
                        r'\b(remote\s+desktop\s+services\s+log)\b',
                        r'\b(rdp\s+brute\s+force\s+attempt)\b'
                    ],
                    "hunting_guidance": "Monitor RDP connection logs, look for unusual RDP connections from internal IPs, check for RDP brute force attempts",
                    "relevance_threshold": 0.7
                },
                {
                    "name": "SSH Hijacking",
                    "patterns": [
                        r'\b(SSH.*Hijack|SSH.*Compromise|SSH.*Lateral)\b',
                        r'\b(SSH.*Key\s+Exchange|SSH.*Authentication\s+Bypass)\b',
                        # Specific SSH patterns
                        r'\b(ssh\s+key\s+exchange\s+failure)\b',
                        r'\b(ssh\s+authentication\s+bypass)\b',
                        r'\b(ssh\s+connection\s+from\s+unusual\s+ip)\b'
                    ],
                    "hunting_guidance": "Monitor SSH connection logs, look for unusual SSH key exchanges, check for SSH authentication bypass attempts",
                    "relevance_threshold": 0.8
                }
            ],
            
            "Persistence": [
                {
                    "name": "Scheduled Task Creation",
                    "patterns": [
                        r'\b(Scheduled\s+Task.*Creation|Task\s+Scheduler.*Attack)\b',
                        r'\b(Cron\s+Job.*Malicious|Automated\s+Task.*Attack)\b',
                        r'\b(Windows\s+Task.*Persistence|Linux\s+Cron.*Persistence)\b',
                        # Specific task patterns
                        r'\b(schtasks\.exe.*create|task\s+scheduler\s+api)\b',
                        r'\b(cron\s+job\s+creation|at\s+command\s+execution)\b',
                        r'\b(scheduled\s+task\s+with\s+suspicious\s+command)\b'
                    ],
                    "hunting_guidance": "Monitor scheduled task creation, look for unusual task schedules, check for tasks running from suspicious locations",
                    "relevance_threshold": 0.7
                },
                {
                    "name": "Registry Persistence",
                    "patterns": [
                        # More specific patterns to avoid false positives
                        r'\b(Registry\s+Run|Run\s+Key|Startup\s+Registry)\b',
                        r'\b(\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)\b',
                        r'\b(Registry\s+modification|Registry\s+key)\b',
                        # Specific registry patterns
                        r'\b(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)\b',
                        r'\b(HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)\b',
                        r'\b(reg\s+add.*run\s+key|registry\s+modification\s+for\s+persistence)\b'
                    ],
                    "hunting_guidance": "Monitor registry modifications to Run keys, look for unusual startup programs, check for registry changes in startup locations",
                    "relevance_threshold": 0.8
                }
            ],
            
            "Execution": [
                {
                    "name": "PowerShell Execution",
                    "patterns": [
                        r'\b(PowerShell.*Execution|PowerShell.*Attack)\b',
                        r'\b(PowerShell.*Script|PowerShell.*Command)\b',
                        # Specific PowerShell patterns
                        r'\b(powershell\.exe.*-enc|powershell.*base64)\b',
                        r'\b(powershell.*-executionpolicy\s+bypass)\b',
                        r'\b(powershell.*invoke-expression|powershell.*iex)\b',
                        r'\b(powershell.*downloadstring|powershell.*webclient)\b'
                    ],
                    "hunting_guidance": "Monitor PowerShell execution logs, look for encoded commands, check for execution policy bypass attempts",
                    "relevance_threshold": 0.8
                },
                {
                    "name": "Process Injection",
                    "patterns": [
                        r'\b(Process.*Injection|Code.*Injection)\b',
                        r'\b(DLL.*Injection|Memory.*Injection)\b',
                        # Specific injection patterns
                        r'\b(createRemoteThread|virtualAllocEx|writeProcessMemory)\b',
                        r'\b(process\s+injection\s+technique|dll\s+injection\s+method)\b',
                        r'\b(memory\s+injection\s+into\s+process)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual process creation, look for DLL injection attempts, check for memory allocation patterns",
                    "relevance_threshold": 0.9
                }
            ],
            
            # Improved Threat Indicators with better precision
            "Threat Indicators": [
                {
                    "name": "Malware Detection",
                    "patterns": [
                        # More specific malware patterns
                        r'\b(identified\s+malware|detected\s+ransomware|found\s+trojan)\b',
                        r'\b(malware\s+analysis|ransomware\s+encryption|trojan\s+behavior)\b',
                        r'\b(malware\s+family|ransomware\s+variant|trojan\s+variant)\b',
                        # Specific malware families
                        r'\b(emotet|trickbot|ryuk|conti|revil)\b',
                        r'\b(lockbit|blackcat|alphv|clop|darkside)\b',
                        # Avoid generic terms
                        r'\b(malware\s+detected|ransomware\s+attack|trojan\s+infection)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual file creation, look for suspicious process behavior, check for unusual network connections",
                    "relevance_threshold": 0.8
                },
                {
                    "name": "Intrusion Indicators",
                    "patterns": [
                        # More specific intrusion patterns
                        r'\b(confirmed\s+intrusion|verified\s+breach|confirmed\s+compromise)\b',
                        r'\b(intrusion\s+detection|breach\s+investigation|compromise\s+analysis)\b',
                        r'\b(intrusion\s+timeline|breach\s+timeline|compromise\s+timeline)\b',
                        # Specific attack patterns
                        r'\b(initial\s+access|privilege\s+escalation|lateral\s+movement)\b',
                        r'\b(command\s+and\s+control|data\s+exfiltration|persistence)\b',
                        # Avoid generic terms
                        r'\b(attack\s+detected|threat\s+identified|security\s+incident)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual system activity, look for unauthorized access attempts, check for unusual user behavior",
                    "relevance_threshold": 0.8
                }
            ],
            
            # High-Value Hunting Patterns with improved precision
            "High-Value Hunting Patterns": [
                {
                    "name": "Process Chain Detection",
                    "patterns": [
                        # Specific process chain patterns
                        r'\b(powershell\.exe.*spawns.*cmd\.exe)\b',
                        r'\b(cmd\.exe.*spawns.*powershell\.exe)\b',
                        r'\b(wscript\.exe.*spawns.*rundll32\.exe)\b',
                        r'\b(process\s+chain.*suspicious|parent.*child.*process.*unusual)\b',
                        r'\b(process\s+hierarchy.*malicious|process\s+tree.*attack)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual parent-child process relationships, look for PowerShell spawning unexpected processes, check for process chains that don't match normal application behavior",
                    "relevance_threshold": 0.9
                },
                {
                    "name": "Registry Persistence",
                    "patterns": [
                        # Specific registry patterns
                        r'\b(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)\b',
                        r'\b(HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)\b',
                        r'\b(registry\s+key\s+persistence|run\s+key\s+malicious)\b',
                        r'\b(registry\s+modification\s+startup|registry\s+key\s+autorun)\b'
                    ],
                    "hunting_guidance": "Monitor registry modifications to Run keys, look for unusual startup programs, check for registry changes in startup locations",
                    "relevance_threshold": 0.9
                },
                {
                    "name": "Command Pattern Detection",
                    "patterns": [
                        # Specific reconnaissance commands
                        r'\b(systeminfo.*command|tasklist.*execution)\b',
                        r'\b(get-service.*powershell|get-process.*enumeration)\b',
                        r'\b(get-netneighbor.*network|get-netroute.*routing)\b',
                        r'\b(get-wmiobject.*system|wmic.*query)\b',
                        r'\b(get-aduser.*enumeration|get-adcomputer.*discovery)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual command execution patterns, look for reconnaissance commands in unexpected contexts, check for PowerShell commands that gather system information",
                    "relevance_threshold": 0.8
                },
                {
                    "name": "File Path Specificity",
                    "patterns": [
                        # Specific suspicious paths
                        r'\b(\\AppData\\Roaming\\php\\php\.exe)\b',
                        r'\b(\\AppData\\Local\\Temp\\\w+\.exe)\b',
                        r'\b(\\Users\\\w+\\AppData\\Roaming\\\w+\.exe)\b',
                        r'\b(suspicious\s+file\s+path|unusual\s+file\s+location)\b',
                        r'\b(malicious\s+file\s+in\s+appdata|executable\s+in\s+temp)\b'
                    ],
                    "hunting_guidance": "Monitor for unusual file creation in suspicious locations, look for executables in AppData directories, check for unusual file paths that don't match normal application behavior",
                    "relevance_threshold": 0.8
                },
                {
                    "name": "Network Infrastructure",
                    "patterns": [
                        # Specific network patterns
                        r'\b(trycloudflare\.com|cloudflare\.com.*abuse)\b',
                        r'\b(suspicious\s+domain.*c2|malicious\s+ip.*command)\b',
                        r'\b(command\s+and\s+control.*server|c2\s+infrastructure)\b',
                        # IP and domain patterns with context
                        r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}.*malicious)\b',
                        r'\b([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*suspicious)\b'
                    ],
                    "hunting_guidance": "Monitor for connections to suspicious domains and IPs, look for abuse of legitimate services like Cloudflare, check for unusual network traffic patterns",
                    "relevance_threshold": 0.8
                },
                {
                    "name": "Sigma Rule Content",
                    "patterns": [
                        # Specific Sigma rule patterns
                        r'\b(sigma\s+rule.*detection|detection\s+rule.*sigma)\b',
                        r'\b(selection:.*|detection:.*|condition:.*)\b',
                        r'\b(mitre\s+att&ck.*t\d{4}\.\d{3})\b',
                        r'\b(parentimage.*|image.*|commandline.*|targetobject.*)\b',
                        r'\b(endswith.*|contains.*|matches_regex.*)\b'
                    ],
                    "hunting_guidance": "This content contains Sigma detection rules - extract and implement these rules in your SIEM, look for MITRE ATT&CK technique mappings, focus on the specific detection logic provided",
                    "relevance_threshold": 0.9
                }
            ]
        }
    
    def _build_threat_actor_patterns(self) -> List[str]:
        """Build patterns for threat actor identification."""
        return [
            r'\b(APT|Advanced\s+Persistent\s+Threat)\s+(\d+|[A-Z]+)\b',
            r'\b(APT|Group)\s+([A-Z0-9]+)\b',
            r'\b([A-Z][a-z]+)\s+(Group|Team|Gang)\b',
            r'\b([A-Z][a-z]+)\s+(APT|Advanced\s+Persistent\s+Threat)\b',
            r'\b(State\s+Sponsored|Nation\s+State|Government\s+Backed)\b',
            r'\b(Cybercrime\s+Group|Hacktivist\s+Group|Cyber\s+Criminal)\b'
        ]
    
    def _build_malware_patterns(self) -> List[str]:
        """Build patterns for malware family identification."""
        return [
            r'\b([A-Z][a-z]+)\s+(RAT|Trojan|Backdoor|Worm|Virus)\b',
            r'\b([A-Z][a-z]+)\s+(Malware|Spyware|Adware)\b',
            r'\b([A-Z][a-z]+)\s+(Loader|Dropper|Packer)\b',
            r'\b([A-Z][a-z]+)\s+(Ransomware|Crypto\s+Locker)\b',
            r'\b([A-Z][a-z]+)\s+(Keylogger|Stealer|Spyware)\b'
        ]
    
    def _build_attack_vector_patterns(self) -> List[str]:
        """Build patterns for attack vector identification."""
        return [
            r'\b(Phishing|Spear\s+Phishing|Whaling)\b',
            r'\b(Social\s+Engineering|Social\s+Manipulation)\b',
            r'\b(Supply\s+Chain|Third\s+Party)\s+(Attack|Compromise)\b',
            r'\b(Watering\s+Hole|Drive\s+By)\s+(Attack|Compromise)\b',
            r'\b(Privilege\s+Escalation|Lateral\s+Movement)\b',
            r'\b(Persistence|Persistence\s+Mechanism)\b',
            r'\b(Command\s+and\s+Control|C2|C&C)\b',
            r'\b(Data\s+Exfiltration|Data\s+Theft)\b'
        ]
    
    def detect_hunting_techniques(self, content: str, article_id: int) -> ThreatHuntingAnalysis:
        """
        Detect huntable techniques from threat intelligence content.
        
        Args:
            content: The article content to analyze
            article_id: ID of the article being analyzed
            
        Returns:
            ThreatHuntingAnalysis object with all detected techniques and hunting guidance
        """
        techniques_by_category = defaultdict(list)
        threat_actors = self._extract_threat_actors(content)
        malware_families = self._extract_malware_families(content)
        attack_vectors = self._extract_attack_vectors(content)
        
        # Detect techniques in each category
        for category, techniques in self.technique_patterns.items():
            for technique in techniques:
                for pattern in technique["patterns"]:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Calculate confidence
                        confidence = self._calculate_technique_confidence(match, content, technique)
                        
                        # Filter out low-confidence matches
                        if confidence < 0.3:  # Minimum confidence threshold
                            continue
                        
                        # Check for duplicate matches (same technique, similar position)
                        if self._is_duplicate_match(match, techniques_by_category[category]):
                            continue
                        
                        hunting_technique = HuntingTechnique(
                            technique_name=technique["name"],
                            category=category,
                            confidence=confidence,
                            context=self._extract_context(content, match.start(), match.end()),
                            matched_text=match.group(),
                            hunting_guidance=technique["hunting_guidance"],
                            position=(match.start(), match.end()),
                            relevance_score=technique.get("relevance_threshold", 0.5)
                        )
                        techniques_by_category[category].append(hunting_technique)
        
        # Calculate overall confidence and hunting priority
        overall_confidence = self._calculate_overall_confidence(techniques_by_category, content)
        hunting_priority = self._determine_hunting_priority(techniques_by_category, overall_confidence)
        
        # Calculate content quality score
        content_quality_score = self.calculate_ttp_quality_score(content)['total_score']
        
        return ThreatHuntingAnalysis(
            article_id=article_id,
            total_techniques=sum(len(techs) for techs in techniques_by_category.values()),
            techniques_by_category=dict(techniques_by_category),
            threat_actors=threat_actors,
            malware_families=malware_families,
            attack_vectors=attack_vectors,
            overall_confidence=overall_confidence,
            hunting_priority=hunting_priority,
            content_quality_score=content_quality_score
        )
    
    def _calculate_technique_confidence(self, match: re.Match, content: str, technique: Dict) -> float:
        """Calculate confidence score for a hunting technique."""
        confidence = 0.5  # Base confidence
        
        # Get context around the match
        context = self._extract_context(content, match.start(), match.end())
        context_lower = context.lower()
        matched_text = match.group()
        
        # Check for noise patterns (reduce confidence if found)
        noise_score = 0
        for noise_pattern in self.noise_patterns:
            if re.search(noise_pattern, context_lower):
                noise_score += 0.1
        confidence -= min(noise_score, 0.3)  # Cap noise reduction at 0.3
        
        # Higher confidence for specific technical context
        technical_indicators = {
            'command_line': ['command line', 'cmd.exe', 'powershell.exe', 'execution'],
            'process': ['process', 'parent process', 'child process', 'process tree'],
            'registry': ['registry', 'reg key', 'hkey', 'registry modification'],
            'network': ['network', 'connection', 'ip address', 'domain', 'http'],
            'file': ['file', 'file path', 'directory', 'file creation'],
            'malware': ['malware', 'trojan', 'ransomware', 'backdoor', 'infection']
        }
        
        # Check which technical context matches
        context_matches = 0
        for category, terms in technical_indicators.items():
            if any(term in context_lower for term in terms):
                context_matches += 1
        
        # Add confidence based on technical context matches
        if context_matches >= 2:
            confidence += 0.3
        elif context_matches == 1:
            confidence += 0.15
        
        # Higher confidence for specific malware families or threat actors
        specific_terms = ['emotet', 'trickbot', 'ryuk', 'conti', 'revil', 'lockbit', 'blackcat']
        if any(term in context_lower for term in specific_terms):
            confidence += 0.2
        
        # Higher confidence for actionable indicators
        actionable_terms = ['ioc', 'indicator', 'hash', 'sha256', 'md5', 'detection']
        if any(term in context_lower for term in actionable_terms):
            confidence += 0.15
        
        # Higher confidence for recent/current threat context
        time_terms = ['2024', '2025', 'recent', 'current', 'ongoing', 'active']
        if any(term in context_lower for term in time_terms):
            confidence += 0.1
        
        # Higher confidence for longer, more specific matches
        if len(matched_text) > 20:
            confidence += 0.1
        elif len(matched_text) > 10:
            confidence += 0.05
        
        # Apply relevance threshold from technique definition
        relevance_threshold = technique.get('relevance_threshold', 0.5)
        if confidence < relevance_threshold:
            confidence = confidence * 0.8  # Reduce confidence if below threshold
        
        return min(max(confidence, 0.1), 1.0)  # Ensure confidence is between 0.1 and 1.0
    
    def _is_duplicate_match(self, match: re.Match, existing_techniques: List[HuntingTechnique]) -> bool:
        """Check if a match is a duplicate of an existing technique."""
        match_text = match.group().lower()
        match_start = match.start()
        
        for existing in existing_techniques:
            # Check if it's the same technique
            if existing.technique_name == match.group():
                # Check if positions are close (within 50 characters)
                if abs(existing.position[0] - match_start) < 50:
                    return True
                
                # Check if matched text is very similar
                if existing.matched_text.lower() == match_text:
                    return True
        
        return False
    
    def _calculate_overall_confidence(self, techniques_by_category: Dict, content: str) -> float:
        """Calculate overall confidence score for the analysis."""
        if not techniques_by_category:
            return 0.0
        
        # Get all techniques
        all_techniques = [tech for techs in techniques_by_category.values() for tech in techs]
        
        # Average confidence of individual techniques
        avg_confidence = sum(tech.confidence for tech in all_techniques) / len(all_techniques)
        
        # Bonus for multiple techniques
        technique_bonus = min(len(all_techniques) * 0.05, 0.2)
        
        # Bonus for content length (more content = more potential for analysis)
        length_bonus = min(len(content) / 10000 * 0.1, 0.1)
        
        return min(avg_confidence + technique_bonus + length_bonus, 1.0)
    
    def _determine_hunting_priority(self, techniques_by_category: Dict, confidence: float) -> str:
        """Determine hunting priority based on techniques and confidence."""
        if not techniques_by_category:
            return "Low"
        
        # Count high-value techniques
        high_value_categories = ["Credential Access", "Lateral Movement", "Persistence", "Command & Control", "High-Value Hunting Patterns"]
        high_value_count = sum(len(techniques_by_category.get(cat, [])) for cat in high_value_categories)
        
        if high_value_count >= 3 or confidence >= 0.8:
            return "High"
        elif high_value_count >= 1 or confidence >= 0.6:
            return "Medium"
        else:
            return "Low"
    
    def calculate_ttp_quality_score(self, content: str) -> Dict[str, Any]:
        """
        Calculate TTP quality score based on the user's analysis framework.
        
        Returns a quality assessment with scoring and recommendations.
        """
        content_lower = content.lower()
        quality_factors = {}
        
        # 1. Sigma Rules Present (15 points)
        sigma_indicators = [
            'sigma rule', 'detection rule', 'hunting rule',
            'selection:', 'detection:', 'condition:',
            'parentimage', 'image', 'commandline', 'targetobject',
            'endswith', 'contains', 'matches_regex'
        ]
        sigma_score = sum(15 if indicator in content_lower else 0 for indicator in sigma_indicators)
        quality_factors['sigma_rules_present'] = min(sigma_score, 15)
        
        # 2. MITRE ATT&CK Mapping (10 points)
        mitre_patterns = [
            r'T\d{4}',  # Basic technique ID
            r'T\d{4}\.\d{3}',  # Sub-technique ID
            r'mitre.*att&ck', r'att&ck.*framework'
        ]
        mitre_score = 0
        for pattern in mitre_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                mitre_score += 5
        quality_factors['mitre_attack_mapping'] = min(mitre_score, 10)
        
        # 3. Process Chains (12 points)
        process_chain_indicators = [
            'parentimage', 'parent process', 'process chain',
            'powershell spawn', 'process spawning', 'child process',
            'process hierarchy', 'parent-child'
        ]
        process_chain_score = sum(3 if indicator in content_lower else 0 for indicator in process_chain_indicators)
        quality_factors['process_chains'] = min(process_chain_score, 12)
        
        # 4. Registry Operations (8 points)
        registry_indicators = [
            'registry run', 'run key', 'startup registry',
            'hkey_current_user', 'hkey_local_machine',
            'software\\microsoft\\windows\\currentversion\\run'
        ]
        registry_score = sum(2 if indicator in content_lower else 0 for indicator in registry_indicators)
        quality_factors['registry_operations'] = min(registry_score, 8)
        
        # 5. Network IOCs (7 points)
        network_indicators = [
            'trycloudflare.com', 'cloudflare.com',
            'suspicious domain', 'malicious ip', 'c2 infrastructure',
            'command and control', 'c2', 'c&c'
        ]
        # Count IP addresses and domains
        ip_count = len(re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', content))
        domain_count = len(re.findall(r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', content))
        network_score = sum(2 if indicator in content_lower else 0 for indicator in network_indicators)
        network_score += min(ip_count, 2) + min(domain_count, 2)
        quality_factors['network_iocs'] = min(network_score, 7)
        
        # 6. File Path Specificity (9 points)
        file_path_indicators = [
            '\\appdata\\roaming\\', '\\appdata\\local\\', '\\temp\\',
            '\\users\\', '\\programdata\\', 'suspicious path',
            'unusual location', 'malicious directory'
        ]
        file_path_score = sum(2 if indicator in content_lower else 0 for indicator in file_path_indicators)
        quality_factors['file_path_specificity'] = min(file_path_score, 9)
        
        # 7. Command Patterns (8 points)
        command_indicators = [
            'systeminfo', 'tasklist', 'get-service', 'get-process',
            'get-netneighbor', 'get-netroute', 'netstat',
            'commandline', 'command line', 'command arguments',
            'get-wmiobject', 'wmic', 'get-computerinfo'
        ]
        command_score = sum(1 if indicator in content_lower else 0 for indicator in command_indicators)
        quality_factors['command_patterns'] = min(command_score, 8)
        
        # 8. Campaign Attribution (6 points)
        campaign_indicators = [
            'campaign', 'threat actor', 'apt', 'group',
            'variant', 'family', 'malware family'
        ]
        campaign_score = sum(2 if indicator in content_lower else 0 for indicator in campaign_indicators)
        quality_factors['campaign_attribution'] = min(campaign_score, 6)
        
        # Calculate total score
        total_score = sum(quality_factors.values())
        quality_factors['total_score'] = total_score
        quality_factors['max_possible'] = 75
        
        # Determine quality level
        if total_score >= 60:
            quality_level = "Excellent"
            recommendation = "This content contains high-value hunting intelligence. Extract all patterns and implement detection rules immediately."
        elif total_score >= 45:
            quality_level = "Good"
            recommendation = "This content has solid hunting value. Focus on the high-scoring areas and implement relevant detection rules."
        elif total_score >= 30:
            quality_level = "Fair"
            recommendation = "This content has some hunting value but needs additional context. Use as supplementary intelligence."
        else:
            quality_level = "Limited"
            recommendation = "This content has minimal hunting value. Consider for general awareness only."
        
        quality_factors['quality_level'] = quality_level
        quality_factors['recommendation'] = recommendation
        
        return quality_factors
    
    def generate_quality_report(self, content: str) -> str:
        """Generate a detailed TTP quality assessment report."""
        quality_data = self.calculate_ttp_quality_score(content)
        
        report = []
        report.append("🔍 TTP Quality Assessment Report")
        report.append("=" * 60)
        report.append(f"Overall Quality: {quality_data['quality_level']}")
        report.append(f"Total Score: {quality_data['total_score']}/{quality_data['max_possible']}")
        report.append("")
        
        report.append("📊 Quality Factor Breakdown:")
        report.append("-" * 40)
        
        # Sort factors by score (highest first)
        sorted_factors = sorted(
            [(k, v) for k, v in quality_data.items() if k not in ['total_score', 'max_possible', 'quality_level', 'recommendation']],
            key=lambda x: x[1],
            reverse=True
        )
        
        for factor, score in sorted_factors:
            factor_name = factor.replace('_', ' ').title()
            report.append(f"{factor_name}: {score}")
        
        report.append("")
        report.append("💡 Recommendation:")
        report.append("-" * 20)
        report.append(quality_data['recommendation'])
        
        report.append("")
        report.append("🎯 High-Value Areas to Focus On:")
        report.append("-" * 40)
        
        # Identify top 3 scoring areas
        top_areas = sorted_factors[:3]
        for factor, score in top_areas:
            if score > 0:
                factor_name = factor.replace('_', ' ').title()
                report.append(f"• {factor_name} (Score: {score})")
        
        report.append("")
        report.append("✅ Assessment Complete!")
        
        return "\n".join(report)
    
    def _extract_threat_actors(self, content: str) -> List[str]:
        """Extract threat actor mentions from content."""
        actors = []
        for pattern in self.threat_actor_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                actors.append(match.group())
        return list(set(actors))
    
    def _extract_malware_families(self, content: str) -> List[str]:
        """Extract malware family mentions from content."""
        families = []
        for pattern in self.malware_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                families.append(match.group())
        return list(set(families))
    
    def _extract_attack_vectors(self, content: str) -> List[str]:
        """Extract attack vector mentions from content."""
        vectors = []
        for pattern in self.attack_vector_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                vectors.append(match.group())
        return list(set(vectors))
    
    def _extract_context(self, content: str, start: int, end: int) -> str:
        """Extract context around a technique match with improved precision."""
        # Try to extract context at sentence boundaries
        context_size = 150  # Increased for better context
        
        # Find sentence boundaries
        start_context = max(0, start - context_size)
        end_context = min(len(content), end + context_size)
        
        # Try to find sentence boundaries
        sentence_start = start_context
        sentence_end = end_context
        
        # Look for sentence start (period, exclamation, question mark followed by space)
        for i in range(start, start_context, -1):
            if i < len(content) and content[i] in '.!?' and i + 1 < len(content) and content[i + 1] in ' \n\t':
                sentence_start = i + 1
                break
        
        # Look for sentence end
        for i in range(end, end_context):
            if i < len(content) and content[i] in '.!?':
                sentence_end = i + 1
                break
        
        # Extract the context
        context = content[sentence_start:sentence_end].strip()
        
        # Add ellipsis if we're not at the beginning/end of content
        if sentence_start > 0:
            context = "..." + context
        if sentence_end < len(content):
            context = context + "..."
        
        # Clean up the context
        context = re.sub(r'\s+', ' ', context)  # Normalize whitespace
        context = context.strip()
        
        # Limit context length if too long
        if len(context) > 300:
            # Try to find a good break point
            words = context.split()
            if len(words) > 20:
                context = ' '.join(words[:20]) + "..."
        
        return context
    
    def generate_hunting_report(self, analysis: ThreatHuntingAnalysis) -> str:
        """Generate a human-readable hunting report."""
        report = []
        report.append(f"Threat Hunting Analysis Report for Article {analysis.article_id}")
        report.append("=" * 60)
        report.append(f"Total Techniques: {analysis.total_techniques}")
        report.append(f"Overall Confidence: {analysis.overall_confidence:.2f}")
        report.append(f"Hunting Priority: {analysis.hunting_priority}")
        report.append(f"Content Quality Score: {analysis.content_quality_score:.2f}")
        report.append("")
        
        if analysis.techniques_by_category:
            report.append("🎯 HUNTABLE TECHNIQUES BY CATEGORY:")
            report.append("=" * 50)
            for category, techniques in analysis.techniques_by_category.items():
                report.append(f"\n📋 {category.upper()}:")
                for i, tech in enumerate(techniques, 1):
                    report.append(f"  {i}. {tech.technique_name}")
                    report.append(f"     Confidence: {tech.confidence:.2f}")
                    report.append(f"     Matched: \"{tech.matched_text}\"")
                    report.append(f"     🎯 Hunting: {tech.hunting_guidance}")
                    report.append("")
        
        if analysis.threat_actors:
            report.append("👥 THREAT ACTORS MENTIONED:")
            report.append("=" * 30)
            for actor in analysis.threat_actors:
                report.append(f"  • {actor}")
            report.append("")
        
        if analysis.malware_families:
            report.append("🦠 MALWARE FAMILIES MENTIONED:")
            report.append("=" * 30)
            for malware in analysis.malware_families:
                report.append(f"  • {malware}")
            report.append("")
        
        if analysis.attack_vectors:
            report.append("⚔️ ATTACK VECTORS IDENTIFIED:")
            report.append("=" * 30)
            for vector in analysis.attack_vectors:
                report.append(f"  • {vector}")
            report.append("")
        
        report.append("✅ Analysis Complete!")
        return "\n".join(report)
