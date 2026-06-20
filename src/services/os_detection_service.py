"""
OS Detection Service for CTI Scraper

Uses CTI-BERT embeddings + RandomForest/LogisticRegression classifier for OS detection.
Falls back to Mistral-7B-Instruct-v0.3 via LMStudio for lightweight inference.
"""

import logging
import pickle
import warnings
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from transformers import AutoModel, AutoTokenizer
from transformers import logging as transformers_logging

logger = logging.getLogger(__name__)

# Suppress transformers warnings about uninitialized pooler weights (harmless for embedding extraction)
transformers_logging.set_verbosity_error()

# OS labels
OS_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]

# Windows OS keyword indicators (for fast keyword-based detection)
WINDOWS_OS_KEYWORDS = [
    # Windows executables
    "powershell.exe",
    "cmd.exe",
    "wmic.exe",
    "reg.exe",
    "rundll32.exe",
    "msiexec.exe",
    "svchost.exe",
    "lsass.exe",
    "winlogon.exe",
    "conhost.exe",
    "wscript.exe",
    "services.exe",
    "findstr.exe",
    "comspec",
    # Windows paths & environment
    "C:\\",
    "D:\\",
    "%WINDIR%",
    "%wintmp%",
    "%APPDATA%",
    "%TEMP%",
    "\\temp\\",
    "\\pipe\\",
    "system32",
    "programdata",
    "appdata",
    # Windows registry
    "hklm",
    "hkcu",
    "HKEY",
    # Windows file extensions
    ".exe",
    ".dll",
    ".bat",
    ".ps1",
    ".lnk",
    # Windows-specific patterns
    "Event ID",
    "EventCode",
    "Sysmon",
    "Windows Event Logs",
    "WMI",
    "schtasks",
    "scheduled tasks",
    # Windows commands
    "icacls",
    "attrib",
    "tasklist",
    "systeminfo",
]


class OSDetectionService:
    """OS detection service using keyword, classifier, then embedding similarity."""

    def __init__(
        self,
        model_name: str = "ibm-research/CTI-BERT",
        classifier_type: str = "random_forest",  # "random_forest" or "logistic_regression"
        use_gpu: bool = True,
        classifier_path: Path | None = None,
    ):
        """
        Initialize OS detection service.

        Args:
            model_name: CTI-BERT model name from HuggingFace
            classifier_type: Type of classifier to use
            use_gpu: Whether to use GPU if available
            classifier_path: Path to saved classifier model (if trained)
        """
        self.model_name = model_name
        self.classifier_type = classifier_type
        self.device = 0 if use_gpu and _TORCH_AVAILABLE and torch.cuda.is_available() else -1
        self.tokenizer = None
        self.model = None
        self.classifier = None
        self._model_loaded = False
        self._classifier_loaded = False
        self.classifier_path = (
            classifier_path or Path(__file__).parent.parent.parent / "models" / "os_detection_classifier.pkl"
        )

        logger.info(f"Initialized OSDetectionService with model '{model_name}' on device {self.device}")

    def _load_model(self) -> None:
        """Load CTI-BERT model and tokenizer."""
        if self._model_loaded:
            return

        try:
            logger.info(f"Loading CTI-BERT model: {self.model_name}")
            # Suppress warnings about uninitialized pooler weights (not used for embeddings)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModel.from_pretrained(self.model_name)
            self.model.eval()

            if self.device >= 0:
                self.model = self.model.to(f"cuda:{self.device}")

            self._model_loaded = True
            logger.info(f"Successfully loaded CTI-BERT model on device {self.device}")


        except Exception as e:
            logger.error(f"Failed to load CTI-BERT model: {e}")
            raise RuntimeError(f"Could not load CTI-BERT model: {e}") from e

    def _get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text using CTI-BERT."""
        if not self._model_loaded:
            self._load_model()

        # Tokenize and encode (truncate to 512 tokens)
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)

        if self.device >= 0:
            inputs = {k: v.to(f"cuda:{self.device}") for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            # Use [CLS] token embedding (first token)
            embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()[0]

        # Normalize
        embedding = embedding / np.linalg.norm(embedding)
        return embedding

    def _check_windows_keywords(self, content: str, min_matches: int = 3) -> dict[str, Any] | None:
        """
        Check for Windows OS keywords in content.

        Args:
            content: Article content
            min_matches: Minimum number of keyword matches required to return Windows

        Returns:
            Dict with operating_system='Windows' if >= min_matches, None otherwise
        """
        if not content:
            return None

        content_lower = content.lower()
        matches = []

        # Check string keywords
        for keyword in WINDOWS_OS_KEYWORDS:
            keyword_lower = keyword.lower()
            # Use word boundaries for better matching
            if keyword_lower in content_lower:
                matches.append(keyword)

        match_count = len(matches)

        if match_count >= min_matches:
            logger.info(f"Windows OS detected via keywords: {match_count} matches (threshold: {min_matches})")
            return {
                "operating_system": "Windows",
                "method": "keyword_match",
                "confidence": "high",
                "keyword_matches": match_count,
                "matched_keywords": matches[:10],  # Return first 10 matches
            }

        logger.debug(f"Windows keyword check: {match_count} matches (threshold: {min_matches}), falling back to BERT")
        return None

    async def detect_os(
        self,
        content: str,
        use_classifier: bool = True,
        min_windows_keywords: int = 3,
    ) -> dict[str, Any]:
        """
        Detect OS from content.

        Detection order (Phase A — entity-driven; embedding paths retired):
        1. Entity KB classification (primary decider).
        2. Windows keyword safety net for low-KB-evidence content (deterministic).
        3. Otherwise Unknown (Phase B will adjudicate this tail with an LLM).

        The BERT classifier/similarity methods remain on the class but are no longer
        called: they were non-discriminative for non-Windows content (every class ~0.5,
        the `Other`/`multiple` tie-break winning). See
        docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md.

        Args:
            content: Article content
            use_classifier: Deprecated/ignored (embedding classifier retired).
            min_windows_keywords: Windows keyword matches for the deterministic safety net.

        Returns:
            Dict with operating_system, method, and confidence
        """
        from src.services.platform_classifier import classify_platforms

        # Step 1: Entity-driven KB classification — explainable, no model, multi-label.
        kb = classify_platforms(content)
        if kb.confidence != "low":
            logger.info(
                f"Platform detected via entity KB: {kb.platforms} "
                f"(confidence={kb.confidence}, scores={kb.scores})"
            )
            return kb.as_os_result()

        # Step 2: deterministic Windows keyword safety net for thin KB evidence.
        keyword_result = self._check_windows_keywords(content, min_matches=min_windows_keywords)
        if keyword_result:
            return keyword_result

        # Step 3: genuinely insufficient signal -> Unknown (no embedding guesswork).
        logger.info(f"Platform classification inconclusive (scores={kb.scores}); returning Unknown")
        return kb.as_os_result()

    def train_classifier(self, training_data: list[dict[str, Any]], save_path: Path | None = None) -> dict[str, Any]:
        """
        Train classifier on labeled data.

        Args:
            training_data: List of dicts with 'content' and 'os_label' keys
            save_path: Path to save trained classifier

        Returns:
            Training metrics
        """
        if not self._model_loaded:
            self._load_model()

        # Prepare training data
        X = []
        y = []

        for item in training_data:
            content = item.get("content", "")
            os_label = item.get("os_label", "Unknown")

            if not content:
                continue

            # Generate embedding
            embedding = self._get_embedding(content[:2000])
            X.append(embedding)

            # Map label to index
            if os_label in OS_LABELS:
                y.append(OS_LABELS.index(os_label))
            else:
                y.append(OS_LABELS.index("Unknown"))

        if len(X) == 0:
            raise ValueError("No valid training data provided")

        X = np.array(X)
        y = np.array(y)

        # Train classifier
        if self.classifier_type == "random_forest":
            self.classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        else:
            self.classifier = LogisticRegression(max_iter=1000, random_state=42)

        self.classifier.fit(X, y)
        self._classifier_loaded = True

        # Save classifier
        save_path = save_path or self.classifier_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            pickle.dump(self.classifier, f)

        logger.info(f"Classifier trained and saved to {save_path}")

        # Calculate training metrics
        train_score = self.classifier.score(X, y)

        return {
            "training_samples": len(X),
            "train_accuracy": float(train_score),
            "classifier_type": self.classifier_type,
            "saved_path": str(save_path),
        }
