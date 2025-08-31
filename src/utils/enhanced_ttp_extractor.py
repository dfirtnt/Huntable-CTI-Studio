"""Enhanced TTP Extraction with Advanced Artifact Coverage.

This module provides enhanced TTP extraction capabilities that integrate with
the advanced quality assessment system, covering comprehensive artifact types
across multiple platforms.
"""

import re
import logging
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class ArtifactType(Enum):
    """Enhanced artifact types for comprehensive coverage."""
    # Windows Artifacts
    PROCESS = "PROCESS"
    CMDLINE = "CMDLINE"
    REGISTRY = "REGISTRY"
    FILE = "FILE"
    EVENTID = "EVENTID"
    NETWORK = "NETWORK"
    WMI = "WMI"
    SERVICES = "SERVICES"
    SCHEDULED_TASKS = "SCHEDULED_TASKS"
    MEMORY = "MEMORY"
    CERTIFICATES = "CERTIFICATES"
    ENVIRONMENT = "ENVIRONMENT"
    MODULES = "MODULES"
    DRIVERS = "DRIVERS"
    USERS = "USERS"
    AUTHENTICATION = "AUTHENTICATION"
    PIPES = "PIPES"
    HANDLES = "HANDLES"
    
    # Linux/Unix Artifacts
    CRON = "CRON"
    BASH_HISTORY = "BASH_HISTORY"
    SUDO = "SUDO"
    SYSCALLS = "SYSCALLS"
    NAMESPACES = "NAMESPACES"
    
    # Cloud/Modern Artifacts
    POWERSHELL_REMOTING = "POWERSHELL_REMOTING"
    CLOUD_API = "CLOUD_API"
    CONTAINER = "CONTAINER"
    KUBERNETES = "KUBERNETES"
    
    # Advanced Persistence
    COM_HIJACKING = "COM_HIJACKING"
    APPINIT_DLL = "APPINIT_DLL"
    IMAGE_FILE_EXECUTION = "IMAGE_FILE_EXECUTION"
    ACCESSIBILITY = "ACCESSIBILITY"
    
    # Threat Intelligence and Social Engineering
    SOCIAL_ENGINEERING = "SOCIAL_ENGINEERING"
    RANSOMWARE = "RANSOMWARE"
    HELP_DESK_ATTACK = "HELP_DESK_ATTACK"
    CONDITIONAL_ACCESS_BYPASS = "CONDITIONAL_ACCESS_BYPASS"
    INDUSTRY_TARGETING = "INDUSTRY_TARGETING"


class CriticalityLevel(Enum):
    """Criticality levels for artifacts."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class EnhancedHuntingTechnique:
    """Enhanced huntable technique with comprehensive metadata."""
    technique_name: str
    artifact_type: ArtifactType
    category: str
    confidence: float
    context: str
    matched_text: str
    hunting_guidance: List[str]
    position: Tuple[int, int]  # (start, end) character positions
    relevance_score: float
    criticality: CriticalityLevel
    platform: str
    ioc_indicators: List[str]
    detection_queries: List[str]


@dataclass
class EnhancedThreatHuntingAnalysis:
    """Enhanced threat hunting analysis results."""
    article_id: int
    total_techniques: int
    techniques_by_category: Dict[str, List[EnhancedHuntingTechnique]]
    techniques_by_platform: Dict[str, List[EnhancedHuntingTechnique]]
    techniques_by_criticality: Dict[str, List[EnhancedHuntingTechnique]]
    threat_actors: List[str]
    malware_families: List[str]
    attack_vectors: List[str]
    overall_confidence: float
    hunting_priority: str  # Critical, High, Medium, Low
    content_quality_score: float
    artifact_coverage: Dict[str, int]  # Platform coverage scores
    hunting_guidance: List[str]
    detection_queries: List[str]


class EnhancedThreatHuntingDetector:
    """Enhanced threat hunting detector with comprehensive artifact coverage."""
    
    def __init__(self):
        """Initialize the enhanced threat hunting detector."""
        self.technique_patterns = self._build_enhanced_hunting_patterns()
        self.threat_actor_patterns = self._build_enhanced_threat_actor_patterns()
        self.malware_patterns = self._build_enhanced_malware_patterns()
        self.attack_vector_patterns = self._build_enhanced_attack_vector_patterns()
        self.detection_patterns = self._build_detection_patterns()
        
        # Noise reduction patterns
        self.noise_patterns = self._build_noise_patterns()
    
    def _build_noise_patterns(self) -> List[str]:
        """Build patterns for common noise words."""
        return [
            r'\b(blog|post|article|report|analysis|study|research)\b',
            r'\b(company|organization|team|group|department)\b',
            r'\b(announcement|news|update|release|version)\b',
            r'\b(conference|event|meeting|presentation|webinar)\b',
            r'\b(partner|customer|client|user|community)\b',
            r'\b(website|page|link|url|address)\b',
            r'\b(contact|email|phone|support|help)\b'
        ]
    
    def _build_enhanced_hunting_patterns(self) -> Dict[str, Dict]:
        """Build comprehensive hunting patterns with enhanced metadata."""
        return {
            # Windows Artifacts
            "PROCESS": {
                "patterns": [
                    (r'\b(process\s+injection|process\s+hollowing|process\s+creation)\b', 0.9),
                    (r'\b(createprocess|startprocess|process\s+spawning)\b', 0.8),
                    (r'\b(lsass\s+memory|lsass\s+process\s+access|credential\s+dumping)\b', 0.9),
                    (r'\b(process\s+memory\s+injection|virtual\s+memory\s+allocation|heap\s+injection)\b', 0.9),
                    (r'\b(parent\s+process\s+spawns|process\s+chain\s+execution)\b', 0.8),
                    (r'\b(process\s+tree\s+manipulation|process\s+hierarchy\s+attack)\b', 0.9)
                ],
                "category": "Execution",
                "criticality": CriticalityLevel.HIGH,
                "platform": "windows",
                "guidance": [
                    "Monitor process creation events",
                    "Look for unusual parent-child process relationships",
                    "Check for process injection indicators",
                    "Monitor LSASS process access"
                ],
                "detection_queries": [
                    "Process Creation where Process Name contains 'rundll32'",
                    "Process Access where Target Process Name contains 'lsass'"
                ]
            },
            "CMDLINE": {
                "patterns": [
                    (r'\b(powershell\s+-enc|powershell\s+-encodedcommand)\b', 0.9),
                    (r'\b(executionpolicy\s+bypass|set-executionpolicy\s+unrestricted)\b', 0.9),
                    (r'\b(iex\s+\(|invoke-expression\s+\(|start-process\s+-windowstyle\s+hidden)\b', 0.9),
                    (r'\b(powershell\s+-nop\s+-w\s+hidden|powershell\s+-windowstyle\s+hidden)\b', 0.9),
                    (r'\b(cmd\.exe\s+/c\s+echo|cmd\s+/c\s+base64)\b', 0.8),
                    (r'\b(rundll32\s+.*\s+.*\s+.*|regsvr32\s+.*\s+/s)\b', 0.9),
                    (r'\b(wscript\.exe\s+.*\.js|wscript\s+.*\.vbs)\b', 0.8),
                    (r'\b(certutil\s+-decode|certutil\s+-decodehex)\b', 0.9)
                ],
                "category": "Execution",
                "criticality": CriticalityLevel.HIGH,
                "platform": "windows",
                "guidance": [
                    "Monitor for encoded PowerShell commands",
                    "Look for execution policy bypasses",
                    "Check for hidden window execution",
                    "Monitor for living-off-the-land techniques"
                ],
                "detection_queries": [
                    "Process Creation where Command Line contains '-enc'",
                    "Process Creation where Command Line contains 'executionpolicy bypass'",
                    "Process Creation where Command Line contains 'iex ('"
                ]
            },
            "REGISTRY": {
                "patterns": [
                    (r'\b(registry\s+key\s+persistence|startup\s+key\s+modification)\b', 0.9),
                    (r'\b(hkey_local_machine\\software\\microsoft\\windows\\currentversion\\run)\b', 0.9),
                    (r'\b(hkey_current_user\\software\\microsoft\\windows\\currentversion\\run)\b', 0.9),
                    (r'\b(image\s+file\s+execution\s+options|ifeo\s+modification)\b', 0.9),
                    (r'\b(reg\s+add.*run|reg\s+add.*runonce)\b', 0.9),
                    (r'\b(registry\s+hijacking|dll\s+search\s+order\s+hijacking)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.HIGH,
                "platform": "windows",
                "guidance": [
                    "Monitor registry modifications",
                    "Check startup keys for persistence",
                    "Look for IFEO modifications",
                    "Monitor registry run keys"
                ],
                "detection_queries": [
                    "Registry Modification where Registry Key contains 'Run'",
                    "Registry Modification where Registry Key contains 'RunOnce'"
                ]
            },
            "WMI": {
                "patterns": [
                    (r'\b(wmi|windows\s+management\s+instrumentation)\b', 0.8),
                    (r'\b(wql\s+query|wmi\s+event|wmi\s+subscription)\b', 0.9),
                    (r'\b(wmiprvse|wmic|wmi\s+provider)\b', 0.8),
                    (r'\b(wmi\s+persistence|wmi\s+event\s+consumer)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "windows",
                "guidance": [
                    "Monitor WMI event subscriptions",
                    "Check for WMI persistence mechanisms",
                    "Look for unusual WQL queries",
                    "Monitor WMI provider activity"
                ],
                "detection_queries": [
                    "WMI Event Subscription Creation",
                    "WMI Event Consumer Creation"
                ]
            },
            "SERVICES": {
                "patterns": [
                    (r'\b(service\s+creation|service\s+modification)\b', 0.8),
                    (r'\b(service\s+hijacking|dll\s+hijacking)\b', 0.9),
                    (r'\b(sc\s+create|new-service|service\s+installation)\b', 0.8),
                    (r'\b(service\s+binary\s+path|service\s+dll)\b', 0.8)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.HIGH,
                "platform": "windows",
                "guidance": [
                    "Monitor service creation events",
                    "Check for service binary path tampering",
                    "Look for DLL hijacking indicators",
                    "Monitor service modifications"
                ],
                "detection_queries": [
                    "Service Creation",
                    "Service Modification where Binary Path changed"
                ]
            },
            "SCHEDULED_TASKS": {
                "patterns": [
                    (r'\b(scheduled\s+task|schtasks|at\s+command)\b', 0.8),
                    (r'\b(task\s+scheduler|task\s+creation)\b', 0.8),
                    (r'\b(trigger|action|persistence\s+mechanism)\b', 0.7),
                    (r'\b(schtasks\s+create|schtasks\s+modify)\b', 0.8)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.HIGH,
                "platform": "windows",
                "guidance": [
                    "Monitor scheduled task creation",
                    "Check for suspicious task triggers",
                    "Look for persistence mechanisms",
                    "Monitor task modifications"
                ],
                "detection_queries": [
                    "Scheduled Task Creation",
                    "Scheduled Task Modification"
                ]
            },
            "MEMORY": {
                "patterns": [
                    (r'\b(memory\s+injection|shellcode|memory\s+dump)\b', 0.9),
                    (r'\b(process\s+memory|virtual\s+memory|heap\s+injection)\b', 0.8),
                    (r'\b(mimikatz|procdump|memory\s+analysis)\b', 0.9),
                    (r'\b(credential\s+dump|lsass\s+memory)\b', 0.9)
                ],
                "category": "Credential Access",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "windows",
                "guidance": [
                    "Monitor for memory injection indicators",
                    "Check for credential dumping activities",
                    "Look for shellcode patterns",
                    "Monitor LSASS memory access"
                ],
                "detection_queries": [
                    "Process Access where Target Process Name contains 'lsass'",
                    "Memory Dump Creation"
                ]
            },
            "CERTIFICATES": {
                "patterns": [
                    (r'\b(code\s+signing|certificate|digital\s+signature)\b', 0.7),
                    (r'\b(self-signed|certificate\s+store|pki)\b', 0.8),
                    (r'\b(certmgr|certutil|certificate\s+installation)\b', 0.8),
                    (r'\b(certificate\s+abuse|code\s+signing\s+bypass)\b', 0.9)
                ],
                "category": "Defense Evasion",
                "criticality": CriticalityLevel.MEDIUM,
                "platform": "windows",
                "guidance": [
                    "Monitor certificate installations",
                    "Check for code signing abuse",
                    "Look for self-signed certificates",
                    "Monitor certificate store modifications"
                ],
                "detection_queries": [
                    "Certificate Installation",
                    "Code Signing Verification Failure"
                ]
            },
            
            # Linux/Unix Artifacts
            "CRON": {
                "patterns": [
                    (r'\b(cron\s+job|crontab|scheduled\s+task)\b', 0.8),
                    (r'\b(at\s+command|batch\s+job|anacron)\b', 0.8),
                    (r'\b(/etc/crontab|/var/spool/cron)\b', 0.9),
                    (r'\b(cron\s+persistence|cron\s+backdoor)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.HIGH,
                "platform": "linux",
                "guidance": [
                    "Monitor crontab modifications",
                    "Check for unusual cron jobs",
                    "Look for persistence mechanisms",
                    "Monitor cron job execution"
                ],
                "detection_queries": [
                    "Cron Job Creation",
                    "Crontab Modification"
                ]
            },
            "BASH_HISTORY": {
                "patterns": [
                    (r'\b(bash\s+history|\.bash_history|command\s+history)\b', 0.7),
                    (r'\b(history\s+manipulation|history\s+deletion)\b', 0.9),
                    (r'\b(histfile|histignore|history\s+size)\b', 0.8),
                    (r'\b(history\s+bypass|history\s+clearing)\b', 0.9)
                ],
                "category": "Defense Evasion",
                "criticality": CriticalityLevel.MEDIUM,
                "platform": "linux",
                "guidance": [
                    "Monitor bash history modifications",
                    "Check for history manipulation",
                    "Look for command execution patterns",
                    "Monitor history file access"
                ],
                "detection_queries": [
                    "Bash History Modification",
                    "History File Deletion"
                ]
            },
            "SUDO": {
                "patterns": [
                    (r'\b(sudo\s+usage|privilege\s+escalation)\b', 0.8),
                    (r'\b(sudoers|visudo|sudo\s+bypass)\b', 0.9),
                    (r'\b(sudo\s+execution|elevated\s+privileges)\b', 0.8),
                    (r'\b(sudo\s+exploit|sudo\s+vulnerability)\b', 0.9)
                ],
                "category": "Privilege Escalation",
                "criticality": CriticalityLevel.HIGH,
                "platform": "linux",
                "guidance": [
                    "Monitor sudo usage patterns",
                    "Check for privilege escalation",
                    "Look for sudo bypass techniques",
                    "Monitor sudoers file modifications"
                ],
                "detection_queries": [
                    "Sudo Command Execution",
                    "Sudoers File Modification"
                ]
            },
            
            # Cloud/Modern Artifacts
            "POWERSHELL_REMOTING": {
                "patterns": [
                    (r'\b(powershell\s+remoting|winrm|psremoting)\b', 0.9),
                    (r'\b(enter-pssession|invoke-command|new-pssession)\b', 0.9),
                    (r'\b(wsman|remote\s+execution|lateral\s+movement)\b', 0.8),
                    (r'\b(psremoting\s+bypass|winrm\s+bypass)\b', 0.9)
                ],
                "category": "Lateral Movement",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "windows",
                "guidance": [
                    "Monitor PowerShell remoting sessions",
                    "Check for lateral movement indicators",
                    "Look for remote execution patterns",
                    "Monitor WinRM connections"
                ],
                "detection_queries": [
                    "PowerShell Remoting Session Creation",
                    "WinRM Connection"
                ]
            },
            "CLOUD_API": {
                "patterns": [
                    (r'\b(aws\s+api|azure\s+api|gcp\s+api)\b', 0.8),
                    (r'\b(cloud\s+credentials|access\s+key|secret\s+key)\b', 0.9),
                    (r'\b(ec2|s3|lambda|functions)\b', 0.7),
                    (r'\b(cloud\s+persistence|cloud\s+backdoor)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.HIGH,
                "platform": "cloud",
                "guidance": [
                    "Monitor cloud API calls",
                    "Check for credential exposure",
                    "Look for unauthorized resource access",
                    "Monitor cloud service modifications"
                ],
                "detection_queries": [
                    "Cloud API Call",
                    "Cloud Credential Access"
                ]
            },
            "CONTAINER": {
                "patterns": [
                    (r'\b(docker\s+run|kubernetes\s+deploy|container\s+runtime)\b', 0.8),
                    (r'\b(container\s+escape|privileged\s+container|root\s+container)\b', 0.9),
                    (r'\b(container\s+persistence|container\s+backdoor|malicious\s+container)\b', 0.9),
                    (r'\b(docker\s+exec|kubectl\s+exec|container\s+execution)\b', 0.8)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.MEDIUM,
                "platform": "container",
                "guidance": [
                    "Monitor container creation",
                    "Check for privileged containers",
                    "Look for container escape attempts",
                    "Monitor container modifications"
                ],
                "detection_queries": [
                    "Container Creation",
                    "Privileged Container Execution"
                ]
            },
            
            # Advanced Persistence
            "COM_HIJACKING": {
                "patterns": [
                    (r'\b(com\s+object|com\s+hijacking|com\s+registration)\b', 0.9),
                    (r'\b(ole|activex|com\s+server)\b', 0.8),
                    (r'\b(registry\s+com|clsid|progid)\b', 0.8),
                    (r'\b(com\s+persistence|com\s+backdoor)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "windows",
                "guidance": [
                    "Monitor COM object registrations",
                    "Check for COM hijacking",
                    "Look for suspicious COM servers",
                    "Monitor COM object access"
                ],
                "detection_queries": [
                    "COM Object Registration",
                    "COM Object Access"
                ]
            },
            "APPINIT_DLL": {
                "patterns": [
                    (r'\b(appinit\s+dll|loadappinit_dlls|dll\s+injection)\b', 0.9),
                    (r'\b(registry\s+load|dll\s+loading|appinit)\b', 0.8),
                    (r'\b(load\s+library|dll\s+hijacking)\b', 0.8),
                    (r'\b(appinit\s+persistence|appinit\s+backdoor)\b', 0.9)
                ],
                "category": "Persistence",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "windows",
                "guidance": [
                    "Monitor AppInit DLL registrations",
                    "Check for DLL hijacking",
                    "Look for suspicious DLL loading",
                    "Monitor DLL load events"
                ],
                "detection_queries": [
                    "AppInit DLL Registration",
                    "DLL Load Event"
                ]
            },
            
            # Social Engineering and Initial Access
            "SOCIAL_ENGINEERING": {
                "patterns": [
                    (r'\b(help\s+desk\s+call|support\s+call|technical\s+support\s+call)\b', 0.9),
                    (r'\b(password\s+reset\s+request|credential\s+reset\s+request)\b', 0.9),
                    (r'\b(phone\s+scam|vishing\s+call|voice\s+phishing\s+call)\b', 0.9),
                    (r'\b(english\s+fluency|language\s+capability|fluent\s+english)\b', 0.7),
                    (r'\b(pretexting\s+call|baiting\s+call|quid\s+pro\s+quo\s+call)\b', 0.8),
                    (r'\b(credential\s+harvesting|password\s+harvesting|credential\s+theft)\b', 0.8),
                    (r'\b(social\s+engineering\s+attack|social\s+engineering\s+technique)\b', 0.8),
                    (r'\b(phishing\s+attack|spear\s+phishing\s+attack)\b', 0.9)
                ],
                "category": "Initial Access",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "multi",
                "guidance": [
                    "Monitor help desk call patterns",
                    "Check for unusual password reset requests",
                    "Look for social engineering indicators",
                    "Monitor vishing attempts"
                ],
                "detection_queries": [
                    "Help Desk Password Reset",
                    "Unusual Phone Call Patterns"
                ]
            },
            
            # Ransomware and Data Exfiltration
            "RANSOMWARE": {
                "patterns": [
                    (r'\b(mass\s+file\s+encryption\s+process|bulk\s+file\s+encryption\s+activity)\b', 0.9),
                    (r'\b(data\s+exfiltration\s+via\s+ftp|data\s+exfiltration\s+via\s+http)\b', 0.9),
                    (r'\b(encryption\s+key\s+generation|ransom\s+note\s+creation)\b', 0.9),
                    (r'\b(raas\s+affiliate\s+portal|ransomware\s+as\s+a\s+service\s+platform)\b', 0.8),
                    (r'\b(dragonforce\s+ransomware\s+execution|lockbit\s+ransomware\s+deployment)\b', 0.9),
                    (r'\b(encryption\s+process\s+monitoring|file\s+encryption\s+detection)\b', 0.9),
                    (r'\b(decryption\s+key\s+delivery|ransom\s+payment\s+processing)\b', 0.8)
                ],
                "category": "Impact",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "multi",
                "guidance": [
                    "Monitor for mass file encryption processes using specific file extensions",
                    "Check for data exfiltration via specific protocols (FTP, HTTP, SMB)",
                    "Look for encryption key generation and ransom note creation",
                    "Monitor for ransomware affiliate portal access"
                ],
                "detection_queries": [
                    "Process Creation where Command Line contains 'cipher' and contains '/e'",
                    "Network Connection where Destination Port contains '21' or '80' and contains large data transfer",
                    "File Creation where File Name contains '.encrypted' or '.locked'",
                    "Registry Modification where Registry Key contains 'HKCU\\Software\\' and contains 'ransom'"
                ]
            },
            
            # Specific Hunting Techniques
            "HELP_DESK_ATTACK": {
                "patterns": [
                    (r'\b(help\s+desk\s+call|support\s+call|technical\s+support)\b', 0.9),
                    (r'\b(password\s+reset\s+request|credential\s+reset)\b', 0.9),
                    (r'\b(phone\s+scam|vishing\s+call|voice\s+phishing)\b', 0.9),
                    (r'\b(english\s+fluency|language\s+capability)\b', 0.7)
                ],
                "category": "Initial Access",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "multi",
                "guidance": [
                    "Monitor help desk call patterns for unusual requests",
                    "Check for password reset requests outside business hours",
                    "Look for calls requesting elevated access",
                    "Monitor for social engineering indicators in support calls"
                ],
                "detection_queries": [
                    "Help Desk Password Reset Request",
                    "Unusual Support Call Pattern"
                ]
            },
            
            "CONDITIONAL_ACCESS_BYPASS": {
                "patterns": [
                    (r'\b(conditional\s+access\s+policy|mfa\s+bypass)\b', 0.9),
                    (r'\b(authentication\s+bypass|access\s+control\s+evasion)\b', 0.8),
                    (r'\b(multi-factor\s+authentication|2fa\s+bypass)\b', 0.8),
                    (r'\b(identity\s+verification\s+bypass)\b', 0.9)
                ],
                "category": "Defense Evasion",
                "criticality": CriticalityLevel.CRITICAL,
                "platform": "multi",
                "guidance": [
                    "Monitor for MFA bypass attempts",
                    "Check for unusual authentication patterns",
                    "Look for conditional access policy violations",
                    "Monitor for identity verification bypasses"
                ],
                "detection_queries": [
                    "MFA Bypass Attempt",
                    "Conditional Access Policy Violation"
                ]
            },
            
            "INDUSTRY_TARGETING": {
                "patterns": [
                    (r'\b(government|retail|insurance|aviation)\s+targeting\b', 0.9),
                    (r'\b(industry\s+wave|targeted\s+attack|sector\s+targeting)\b', 0.8),
                    (r'\b(peer\s+targeting|competitor\s+attack)\b', 0.8),
                    (r'\b(specific\s+industry|vertical\s+targeting)\b', 0.7)
                ],
                "category": "Reconnaissance",
                "criticality": CriticalityLevel.HIGH,
                "platform": "multi",
                "guidance": [
                    "Monitor for industry-specific targeting indicators",
                    "Check for attacks against peer organizations",
                    "Look for sector-specific threat intelligence",
                    "Monitor for industry wave attacks"
                ],
                "detection_queries": [
                    "Industry-Specific Targeting",
                    "Peer Organization Attack"
                ]
            }
        }
    
    def _build_enhanced_threat_actor_patterns(self) -> List[Tuple[str, float]]:
        """Build enhanced threat actor patterns."""
        return [
            (r'\b(apt\d+|advanced\s+persistent\s+threat)\b', 0.9),
            (r'\b(cyber\s+group|hacking\s+group|threat\s+actor)\b', 0.8),
            (r'\b(attacker|adversary|malicious\s+actor)\b', 0.7),
            (r'\b(apt\d+[a-z]|apt\d+-\d+)\b', 0.9),
            (r'\b(cyber\s+espionage|state\s+sponsored)\b', 0.8)
        ]
    
    def _build_enhanced_malware_patterns(self) -> List[Tuple[str, float]]:
        """Build enhanced malware patterns."""
        return [
            (r'\b(ransomware|trojan|backdoor|keylogger)\b', 0.9),
            (r'\b(malware|virus|worm|rootkit)\b', 0.8),
            (r'\b(rat|remote\s+access\s+trojan)\b', 0.9),
            (r'\b(botnet|ddos|distributed\s+denial\s+of\s+service)\b', 0.8),
            (r'\b(cryptominer|crypto\s+mining|mining\s+malware)\b', 0.8)
        ]
    
    def _build_enhanced_attack_vector_patterns(self) -> List[Tuple[str, float]]:
        """Build enhanced attack vector patterns."""
        return [
            (r'\b(phishing|spear\s+phishing|social\s+engineering)\b', 0.9),
            (r'\b(exploit|vulnerability|cve-|zero-day)\b', 0.9),
            (r'\b(watering\s+hole|supply\s+chain|drive-by)\b', 0.8),
            (r'\b(credential\s+stuffing|password\s+spraying)\b', 0.8),
            (r'\b(man\s+in\s+the\s+middle|mitm)\b', 0.8)
        ]
    
    def _build_detection_patterns(self) -> List[Tuple[str, float]]:
        """Build detection and hunting patterns."""
        return [
            (r'\b(sigma\s+rule|yara\s+rule|detection\s+rule)\b', 0.9),
            (r'\b(splunk|elasticsearch|kql|spl|hunting\s+query)\b', 0.8),
            (r'\b(ioc|indicator\s+of\s+compromise)\b', 0.8),
            (r'\b(hash|sha256|md5|sha1)\b', 0.7),
            (r'\b(ip\s+address|domain|url|email)\b', 0.7)
        ]
    
    def extract_enhanced_techniques(self, content: str) -> EnhancedThreatHuntingAnalysis:
        """Extract enhanced hunting techniques from content."""
        try:
            techniques = []
            threat_actors = []
            malware_families = []
            attack_vectors = []
            detection_queries = []
            
            # Extract techniques by category
            for category, config in self.technique_patterns.items():
                for pattern, confidence in config["patterns"]:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        matched_text = match.group()
                        
                        # Filter out matches that are too short (less than 20 characters)
                        if len(matched_text) < 20:
                            continue
                            
                        technique = EnhancedHuntingTechnique(
                            technique_name=category,
                            artifact_type=ArtifactType(category),
                            category=config["category"],
                            confidence=confidence,
                            context=match.group(),
                            matched_text=matched_text,
                            hunting_guidance=config["guidance"].copy(),
                            position=(match.start(), match.end()),
                            relevance_score=confidence,
                            criticality=config["criticality"],
                            platform=config["platform"],
                            ioc_indicators=self._extract_ioc_indicators(match.group()),
                            detection_queries=config["detection_queries"].copy()
                        )
                        techniques.append(technique)
            
            # Extract threat actors
            for pattern, confidence in self.threat_actor_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                threat_actors.extend(matches)
            
            # Extract malware families
            for pattern, confidence in self.malware_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                malware_families.extend(matches)
            
            # Extract attack vectors
            for pattern, confidence in self.attack_vector_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                attack_vectors.extend(matches)
            
            # Extract detection queries
            for pattern, confidence in self.detection_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                detection_queries.extend(matches)
            
            # Organize techniques by category, platform, and criticality
            techniques_by_category = defaultdict(list)
            techniques_by_platform = defaultdict(list)
            techniques_by_criticality = defaultdict(list)
            
            for technique in techniques:
                techniques_by_category[technique.category].append(technique)
                techniques_by_platform[technique.platform].append(technique)
                techniques_by_criticality[technique.criticality.value].append(technique)
            
            # Calculate artifact coverage
            artifact_coverage = self._calculate_artifact_coverage(techniques_by_platform)
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(techniques)
            
            # Determine hunting priority
            hunting_priority = self._determine_hunting_priority(techniques)
            
            # Generate hunting guidance
            hunting_guidance = self._generate_hunting_guidance(techniques)
            
            return EnhancedThreatHuntingAnalysis(
                article_id=0,  # Will be set by caller
                total_techniques=len(techniques),
                techniques_by_category=dict(techniques_by_category),
                techniques_by_platform=dict(techniques_by_platform),
                techniques_by_criticality=dict(techniques_by_criticality),
                threat_actors=list(set(threat_actors)),
                malware_families=list(set(malware_families)),
                attack_vectors=list(set(attack_vectors)),
                overall_confidence=overall_confidence,
                hunting_priority=hunting_priority,
                content_quality_score=self._calculate_content_quality_score(techniques),
                artifact_coverage=artifact_coverage,
                hunting_guidance=hunting_guidance,
                detection_queries=list(set(detection_queries))
            )
            
        except Exception as e:
            logger.error(f"Enhanced technique extraction failed: {e}")
            return self._create_default_analysis()
    
    def _extract_ioc_indicators(self, text: str) -> List[str]:
        """Extract IOC indicators from text."""
        ioc_patterns = [
            r'\b([a-fA-F0-9]{64})\b',  # SHA256
            r'\b([a-fA-F0-9]{32})\b',  # MD5
            r'\b([a-fA-F0-9]{40})\b',  # SHA1
            r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',  # IP
            r'\b([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',  # Domain
            r'\b(https?://[^\s]+)\b',  # URL
            r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'  # Email
        ]
        
        indicators = []
        for pattern in ioc_patterns:
            matches = re.findall(pattern, text)
            indicators.extend(matches)
        
        return indicators
    
    def _calculate_artifact_coverage(self, techniques_by_platform: Dict[str, List[EnhancedHuntingTechnique]]) -> Dict[str, int]:
        """Calculate artifact coverage by platform."""
        coverage = {
            "windows": 0,
            "linux": 0,
            "macos": 0,
            "cloud": 0,
            "container": 0
        }
        
        for platform, techniques in techniques_by_platform.items():
            if platform in coverage:
                # Calculate coverage based on number and criticality of techniques
                score = 0
                for technique in techniques:
                    if technique.criticality == CriticalityLevel.CRITICAL:
                        score += 20
                    elif technique.criticality == CriticalityLevel.HIGH:
                        score += 15
                    elif technique.criticality == CriticalityLevel.MEDIUM:
                        score += 10
                    else:
                        score += 5
                
                coverage[platform] = min(score, 100)
        
        return coverage
    
    def _calculate_overall_confidence(self, techniques: List[EnhancedHuntingTechnique]) -> float:
        """Calculate overall confidence based on technique confidence scores."""
        if not techniques:
            return 0.0
        
        total_confidence = sum(technique.confidence for technique in techniques)
        return min(total_confidence / len(techniques), 1.0)
    
    def _determine_hunting_priority(self, techniques: List[EnhancedHuntingTechnique]) -> str:
        """Determine hunting priority based on techniques found."""
        if not techniques:
            return "Low"
        
        critical_count = sum(1 for t in techniques if t.criticality == CriticalityLevel.CRITICAL)
        high_count = sum(1 for t in techniques if t.criticality == CriticalityLevel.HIGH)
        
        if critical_count >= 2:
            return "Critical"
        elif critical_count >= 1 or high_count >= 3:
            return "High"
        elif high_count >= 1:
            return "Medium"
        else:
            return "Low"
    
    def _calculate_content_quality_score(self, techniques: List[EnhancedHuntingTechnique]) -> float:
        """Calculate content quality score based on techniques."""
        if not techniques:
            return 0.0
        
        # Score based on number and quality of techniques
        score = 0
        for technique in techniques:
            score += technique.relevance_score * 10
        
        return min(score, 100.0)
    
    def _generate_hunting_guidance(self, techniques: List[EnhancedHuntingTechnique]) -> List[str]:
        """Generate comprehensive hunting guidance."""
        guidance = []
        
        # Collect guidance from all techniques
        for technique in techniques:
            guidance.extend(technique.hunting_guidance)
        
        # Add general guidance based on technique count
        if len(techniques) >= 5:
            guidance.append("High technique coverage - prioritize for immediate hunting")
        elif len(techniques) >= 2:
            guidance.append("Moderate technique coverage - include in regular hunting rotation")
        else:
            guidance.append("Low technique coverage - review for additional context")
        
        return list(set(guidance))  # Remove duplicates
    
    def _create_default_analysis(self) -> EnhancedThreatHuntingAnalysis:
        """Create default analysis when extraction fails."""
        return EnhancedThreatHuntingAnalysis(
            article_id=0,
            total_techniques=0,
            techniques_by_category={},
            techniques_by_platform={},
            techniques_by_criticality={},
            threat_actors=[],
            malware_families=[],
            attack_vectors=[],
            overall_confidence=0.0,
            hunting_priority="Low",
            content_quality_score=0.0,
            artifact_coverage={
                "windows": 0,
                "linux": 0,
                "macos": 0,
                "cloud": 0,
                "container": 0
            },
            hunting_guidance=["Analysis failed - review content manually"],
            detection_queries=[]
        )
    
    def generate_enhanced_report(self, analysis: EnhancedThreatHuntingAnalysis) -> str:
        """Generate detailed enhanced analysis report."""
        report = []
        report.append("🔍 Enhanced Threat Hunting Analysis Report")
        report.append("=" * 60)
        report.append(f"Total Techniques: {analysis.total_techniques}")
        report.append(f"Overall Confidence: {analysis.overall_confidence:.2f}")
        report.append(f"Hunting Priority: {analysis.hunting_priority}")
        report.append(f"Content Quality Score: {analysis.content_quality_score:.1f}")
        report.append("")
        
        report.append("📊 Technique Breakdown by Category:")
        report.append("-" * 40)
        for category, techniques in analysis.techniques_by_category.items():
            report.append(f"{category}: {len(techniques)} techniques")
        report.append("")
        
        report.append("🖥️ Platform Coverage:")
        report.append("-" * 20)
        for platform, score in analysis.artifact_coverage.items():
            report.append(f"{platform.title()}: {score}/100")
        report.append("")
        
        report.append("⚡ Criticality Breakdown:")
        report.append("-" * 25)
        for criticality, techniques in analysis.techniques_by_criticality.items():
            report.append(f"{criticality}: {len(techniques)} techniques")
        report.append("")
        
        if analysis.threat_actors:
            report.append("🎭 Threat Actors:")
            report.append("-" * 15)
            for actor in analysis.threat_actors:
                report.append(f"• {actor}")
            report.append("")
        
        if analysis.malware_families:
            report.append("🦠 Malware Families:")
            report.append("-" * 18)
            for malware in analysis.malware_families:
                report.append(f"• {malware}")
            report.append("")
        
        if analysis.attack_vectors:
            report.append("🎯 Attack Vectors:")
            report.append("-" * 16)
            for vector in analysis.attack_vectors:
                report.append(f"• {vector}")
            report.append("")
        
        report.append("💡 Hunting Guidance:")
        report.append("-" * 18)
        for guidance in analysis.hunting_guidance:
            report.append(f"• {guidance}")
        report.append("")
        
        if analysis.detection_queries:
            report.append("🔍 Detection Queries:")
            report.append("-" * 18)
            for query in analysis.detection_queries:
                report.append(f"• {query}")
            report.append("")
        
        report.append("✅ Analysis Complete!")
        
        return "\n".join(report)

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
            recommendation = "This content has good hunting value. Review and implement key detection patterns."
        elif total_score >= 30:
            quality_level = "Fair"
            recommendation = "This content has some hunting value. Focus on the most specific indicators."
        else:
            quality_level = "Limited"
            recommendation = "This content has limited hunting value. Consider for general awareness only."
        
        quality_factors['quality_level'] = quality_level
        quality_factors['recommendation'] = recommendation
        
        return quality_factors


# Convenience function for easy integration
def extract_enhanced_techniques(content: str) -> EnhancedThreatHuntingAnalysis:
    """
    Convenience function to extract enhanced hunting techniques.
    
    Args:
        content: Article content to analyze
        
    Returns:
        EnhancedThreatHuntingAnalysis with comprehensive results
    """
    detector = EnhancedThreatHuntingDetector()
    return detector.extract_enhanced_techniques(content)
