"""
Huntable Windows Detection Service

Detects if an article contains Windows-based huntables using:
1. Trained ML classifier (LOLBAS + BERT embeddings)
2. Perfect discriminator rule-based check (additional signal)
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import re
from sklearn.preprocessing import StandardScaler

from src.services.os_detection_service import OSDetectionService

logger = logging.getLogger(__name__)


# Perfect discriminators for rule-based check
PERFECT_DISCRIMINATORS = [
    # Windows executables & commands
    'rundll32.exe', 'comspec', 'msiexec.exe', 'wmic.exe', 'iex', 'findstr.exe',
    'powershell.exe', 'svchost.exe', 'lsass.exe', 'reg.exe',
    'winlogon.exe', 'conhost.exe', 'wscript.exe', 'services.exe', 'fodhelper',
    # Windows paths & environment
    'hklm', 'appdata', 'programdata', 'wbem',
    '.lnk', 'd:\\', 'c:\\', '.iso', 'mz',
    'windir', 'wintmp', '\\temp\\', '\\pipe\\',
    '%windir%', '%wintmp%',
    # PowerShell attack techniques
    'invoke-mimikatz', 'hashdump', 'invoke-shellcode', 'invoke-eternalblue',
    'frombase64string', 'memorystream', 'downloadstring',
    '-accepteula',
    # Telemetry & detection
    'eventcode', '2>&1',
    'tasklist', 'icacls', 'attrib',
    # PowerShell/scripting
    'invoke-', '-encodedcommand',
    'dclist',
    'adfind',
    # System indicators
    '-comobject', 'chcp',
    'hkcu', 'system32',
    'cmd', 'xor',
    # System operations
    'system.io', 'new-object', 'streamreader', 'bytearray',
    '127.0.0.1', '>1', 'admin$', 'c$',
    'mppreference', 'msbuild',
    'interopservices.marshal'
]

# Cmd.exe obfuscation regex patterns
OBFUSCATION_PATTERNS = [
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
]


class HuntableWindowsService:
    """
    Service for detecting Windows huntables in articles.
    
    Uses hybrid approach:
    1. ML classifier (LOLBAS keywords + CTI-BERT embeddings)
    2. Perfect discriminator rule-based check (additional signal)
    """
    
    def __init__(
        self,
        model_path: Optional[Path] = None,
        scaler_path: Optional[Path] = None
    ):
        """
        Initialize service.
        
        Args:
            model_path: Path to trained classifier (default: models/huntable_windows_classifier.pkl)
            scaler_path: Path to feature scaler (default: models/huntable_windows_scaler.pkl)
        """
        self.model_path = model_path or Path(__file__).parent.parent.parent / "models" / "huntable_windows_classifier.pkl"
        self.scaler_path = scaler_path or Path(__file__).parent.parent.parent / "models" / "huntable_windows_scaler.pkl"
        
        self.classifier = None
        self.scaler = None
        self.os_service = None
        self._model_loaded = False
    
    def _load_model(self):
        """Load classifier and scaler if available."""
        if self._model_loaded:
            return
        
        if self.model_path.exists() and self.scaler_path.exists():
            try:
                with open(self.model_path, 'rb') as f:
                    self.classifier = pickle.load(f)
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self._model_loaded = True
                logger.info(f"Loaded huntable Windows classifier from {self.model_path}")
            except Exception as e:
                logger.warning(f"Failed to load classifier: {e}")
        
        # Initialize OS detection service for embeddings
        if not self.os_service:
            self.os_service = OSDetectionService()
    
    def check_perfect_discriminators(self, content: str) -> Dict[str, Any]:
        """
        Rule-based check using perfect discriminators.
        
        Returns:
            Dict with has_windows_huntables (bool) and matched_patterns (list)
        """
        content_lower = content.lower()
        matched_patterns = []
        
        # Check string patterns
        for pattern in PERFECT_DISCRIMINATORS:
            if pattern.lower() in content_lower:
                matched_patterns.append(pattern)
        
        # Check regex patterns
        for pattern in OBFUSCATION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                matched_patterns.append(f"regex:{pattern[:50]}")
        
        has_windows_huntables = len(matched_patterns) > 0
        
        return {
            "has_windows_huntables": has_windows_huntables,
            "matched_patterns": matched_patterns,
            "match_count": len(matched_patterns)
        }
    
    def _extract_keyword_features(self, article_metadata: Dict[str, Any]) -> np.ndarray:
        """Extract keyword features for ML classifier (matches training)."""
        lolbas_count = len(article_metadata.get('lolbas_matches', []) or [])
        perfect_count = len(article_metadata.get('perfect_keyword_matches', []) or [])
        good_count = len(article_metadata.get('good_keyword_matches', []) or [])
        
        # Key LOLBAS binaries
        key_lolbas = [
            'powershell.exe', 'cmd.exe', 'wmic.exe', 'certutil.exe',
            'schtasks.exe', 'reg.exe', 'rundll32.exe', 'bitsadmin.exe'
        ]
        
        content = article_metadata.get('content', '')[:2000].lower()
        key_lolbas_present = [
            1 if exe in content else 0 for exe in key_lolbas
        ]
        
        features = np.array([
            lolbas_count,
            perfect_count,
            good_count,
            *key_lolbas_present
        ], dtype=np.float32)
        
        return features
    
    def detect_windows_huntables(
        self,
        content: str,
        article_metadata: Optional[Dict[str, Any]] = None,
        use_ml_classifier: bool = True,
        use_perfect_discriminators: bool = True
    ) -> Dict[str, Any]:
        """
        Detect if article contains Windows huntables.
        
        Args:
            content: Article content
            article_metadata: Optional article metadata (for keyword counts)
            use_ml_classifier: Use trained ML classifier
            use_perfect_discriminators: Use rule-based perfect discriminator check
        
        Returns:
            Dict with:
            - has_windows_huntables (bool)
            - confidence (float, 0-1)
            - method (str): 'ml_classifier', 'perfect_discriminators', 'combined'
            - ml_prediction (optional)
            - perfect_discriminator_check (optional)
        """
        results = {
            "has_windows_huntables": False,
            "confidence": 0.0,
            "method": "unknown"
        }
        
        # Rule-based check (perfect discriminators)
        perfect_check = None
        if use_perfect_discriminators:
            perfect_check = self.check_perfect_discriminators(content)
            if perfect_check["has_windows_huntables"]:
                results["has_windows_huntables"] = True
                results["confidence"] = 1.0  # Perfect discriminators = high confidence
                results["method"] = "perfect_discriminators"
                results["perfect_discriminator_check"] = perfect_check
                return results
        
        # ML classifier check
        ml_prediction = None
        if use_ml_classifier:
            self._load_model()
            
            if self.classifier and self.scaler and article_metadata:
                try:
                    # Extract features
                    keyword_features = self._extract_keyword_features(article_metadata)
                    embedding = self.os_service._get_embedding(content[:2000])
                    
                    # Combine features
                    features = np.hstack([keyword_features, embedding]).reshape(1, -1)
                    
                    # Scale and predict
                    features_scaled = self.scaler.transform(features)
                    prediction = self.classifier.predict(features_scaled)[0]
                    probability = self.classifier.predict_proba(features_scaled)[0][1]
                    
                    ml_prediction = {
                        "prediction": int(prediction),
                        "probability": float(probability)
                    }
                    
                    if prediction == 1:
                        results["has_windows_huntables"] = True
                        results["confidence"] = probability
                        results["method"] = "ml_classifier"
                        results["ml_prediction"] = ml_prediction
                except Exception as e:
                    logger.warning(f"ML classifier failed: {e}")
        
        # Combined result
        if perfect_check and ml_prediction:
            # If both agree, use higher confidence
            if perfect_check["has_windows_huntables"] or ml_prediction["prediction"] == 1:
                results["has_windows_huntables"] = True
                results["confidence"] = max(
                    perfect_check.get("confidence", 0.0),
                    ml_prediction.get("probability", 0.0)
                )
                results["method"] = "combined"
                results["ml_prediction"] = ml_prediction
                results["perfect_discriminator_check"] = perfect_check
        
        return results

