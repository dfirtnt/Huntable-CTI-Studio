"""
OS Detection Service for CTI Scraper

Uses CTI-BERT embeddings + RandomForest/LogisticRegression classifier for OS detection.
Falls back to Mistral-7B-Instruct-v0.3 via LMStudio for lightweight inference.
"""

import logging
import os
import pickle
import warnings
from typing import Dict, Any, Optional, List
from pathlib import Path
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from transformers import logging as transformers_logging
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
import httpx
import asyncio

logger = logging.getLogger(__name__)

# Suppress transformers warnings about uninitialized pooler weights (harmless for embedding extraction)
transformers_logging.set_verbosity_error()

# OS labels
OS_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]

# OS-specific indicator texts for embedding comparison
OS_INDICATORS = {
    "Windows": [
        "powershell.exe cmd.exe wmic.exe reg.exe schtasks.exe",
        "HKCU HKLM HKEY registry paths",
        "C:\\ %APPDATA% %TEMP% %SYSTEMROOT% Windows file paths",
        "Event ID 4688 4697 4698 Sysmon Windows Event Logs",
        "Windows services scheduled tasks WMI",
        ".exe .dll .bat .ps1 Windows file extensions"
    ],
    "Linux": [
        "bash sh systemd cron apt yum systemctl",
        "/etc/ /var/ /tmp/ /home/ /usr/bin/ Linux file paths",
        "apt yum dpkg rpm Linux package managers",
        "systemd init.d upstart Linux init systems",
        ".sh .deb .rpm Linux file extensions"
    ],
    "MacOS": [
        "osascript launchctl plutil defaults macOS commands",
        "/Library/ ~/Library/ /Applications/ /System/ macOS file paths",
        ".pkg .dmg .app macOS package formats",
        "LaunchAgents LaunchDaemons macOS launch agents",
        "CoreFoundation Cocoa macOS APIs"
    ],
    "Other": [
        "network protocols HTTP HTTPS TCP UDP DNS",
        "cloud platforms AWS Azure GCP infrastructure",
        "web applications APIs REST GraphQL",
        "container technologies Docker Kubernetes",
        "virtualization VMware Hyper-V VirtualBox",
        "firmware BIOS UEFI embedded systems",
        "IoT devices routers switches network equipment",
        "cross-platform frameworks Electron Node.js Python",
        "mobile platforms Android iOS",
        "hardware vulnerabilities CPU GPU firmware"
    ],
    "multiple": [
        "Windows Linux MacOS cross-platform multi-OS",
        "multiple operating systems different platforms",
        "Windows and Linux Windows and MacOS Linux and MacOS",
        "cross-platform attack multi-platform malware",
        "works on Windows Linux MacOS all platforms",
        "platform-agnostic OS-independent"
    ]
}


class OSDetectionService:
    """OS detection service using CTI-BERT + classifier with Mistral-7B fallback."""
    
    def __init__(
        self,
        model_name: str = "ibm-research/CTI-BERT",
        classifier_type: str = "random_forest",  # "random_forest" or "logistic_regression"
        use_gpu: bool = True,
        classifier_path: Optional[Path] = None
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
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        self.tokenizer = None
        self.model = None
        self.classifier = None
        self._model_loaded = False
        self._classifier_loaded = False
        self.os_indicator_embeddings = {}
        self.classifier_path = classifier_path or Path(__file__).parent.parent.parent / "models" / "os_detection_classifier.pkl"
        
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
            
            # Pre-compute OS indicator embeddings
            self._precompute_os_embeddings()
            
        except Exception as e:
            logger.error(f"Failed to load CTI-BERT model: {e}")
            raise RuntimeError(f"Could not load CTI-BERT model: {e}")
    
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
    
    def _precompute_os_embeddings(self):
        """Pre-compute embeddings for OS indicators."""
        logger.info("Pre-computing OS indicator embeddings...")
        for os_name, indicators in OS_INDICATORS.items():
            # Combine all indicators for this OS
            combined_text = " ".join(indicators)
            embedding = self._get_embedding(combined_text)
            self.os_indicator_embeddings[os_name] = embedding
        logger.info("OS indicator embeddings computed")
    
    def _load_classifier(self) -> bool:
        """Load trained classifier if available."""
        if self._classifier_loaded:
            return True
        
        if self.classifier_path.exists():
            try:
                logger.info(f"Loading classifier from {self.classifier_path}")
                with open(self.classifier_path, 'rb') as f:
                    self.classifier = pickle.load(f)
                self._classifier_loaded = True
                logger.info("Classifier loaded successfully")
                return True
            except Exception as e:
                logger.warning(f"Failed to load classifier: {e}")
                return False
        else:
            logger.info("No trained classifier found, will use similarity-based detection")
            return False
    
    def _detect_with_classifier(self, content: str) -> Optional[Dict[str, Any]]:
        """Detect OS using trained classifier."""
        if not self._load_classifier() or self.classifier is None:
            return None
        
        try:
            # Generate embedding for content
            content_sample = content[:2000]  # Use first 2000 chars
            content_embedding = self._get_embedding(content_sample)
            
            # Predict using classifier
            prediction = self.classifier.predict([content_embedding])[0]
            probabilities = None
            if hasattr(self.classifier, 'predict_proba'):
                probabilities = self.classifier.predict_proba([content_embedding])[0]
            
            # Map prediction to OS label
            if isinstance(prediction, (int, np.integer)):
                # If classifier returns index
                if 0 <= prediction < len(OS_LABELS):
                    os_label = OS_LABELS[prediction]
                else:
                    os_label = "Unknown"
            else:
                os_label = str(prediction)
            
            confidence = float(probabilities.max()) if probabilities is not None else None
            
            return {
                "operating_system": os_label,
                "method": "classifier",
                "confidence": confidence,
                "probabilities": probabilities.tolist() if probabilities is not None else None
            }
        except Exception as e:
            logger.error(f"Classifier detection failed: {e}")
            return None
    
    def _detect_with_similarity(self, content: str) -> Dict[str, Any]:
        """Detect OS using similarity-based approach (fallback when no classifier)."""
        if not self._model_loaded:
            self._load_model()
        
        # Generate embedding for article content
        content_sample = content[:2000]
        content_embedding = self._get_embedding(content_sample)
        
        # Calculate similarity to each OS
        similarities = {}
        for os_name, os_embedding in self.os_indicator_embeddings.items():
            similarity = sklearn_cosine_similarity(
                content_embedding.reshape(1, -1),
                os_embedding.reshape(1, -1)
            )[0][0]
            similarities[os_name] = float(similarity)
        
        # Determine OS based on similarities
        max_similarity = max(similarities.values())
        max_os = max(similarities, key=similarities.get)
        
        # Sort similarities to find the gap between top OSes
        sorted_sims = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        top_os, top_sim = sorted_sims[0]
        second_os, second_sim = sorted_sims[1] if len(sorted_sims) > 1 else (None, 0)
        
        # Decision logic:
        # 1. If max similarity is very high (>0.8) and significantly higher than second (>0.05 gap), use that OS
        # 2. If multiple OSes have high similarity (>0.75) and are close to each other (<0.05 gap), classify as "multiple"
        # 3. If max similarity > 0.6, use that OS
        # 4. Otherwise, "Unknown"
        
        gap_to_second = top_sim - second_sim if second_sim > 0 else top_sim
        
        # Decision logic:
        # 1. If max similarity > 0.8, prefer that OS unless second is very close (<0.02 gap)
        # 2. If max similarity > 0.75 and gap > 0.02, use that OS
        # 3. If multiple OSes are very close (<0.02 gap) and all > 0.75, classify as "multiple"
        # 4. If max similarity > 0.6, use that OS
        # 5. Otherwise, "Unknown"
        
        if max_similarity > 0.8:
            # High confidence - prefer the top OS unless second is extremely close (<0.5% gap)
            if gap_to_second < 0.005:
                # Top OSes are within 0.5% - likely truly multi-platform
                close_oses = [os for os, sim in similarities.items() if sim > max_similarity - 0.005]
                detected_os = "multiple" if len(close_oses) > 1 else max_os
            else:
                # Clear winner - use the top OS
                detected_os = max_os
        elif max_similarity > 0.75:
            # Medium-high confidence
            if gap_to_second < 0.02:
                # Top OSes are very close - check if multiple qualify
                high_similarity_oses = [os for os, sim in similarities.items() if sim > 0.75]
                detected_os = "multiple" if len(high_similarity_oses) > 1 else max_os
            else:
                detected_os = max_os
        elif max_similarity > 0.6:
            detected_os = max_os
        else:
            detected_os = "Unknown"
        
        return {
            "operating_system": detected_os,
            "method": "similarity",
            "max_similarity": float(max_similarity),
            "similarities": similarities,
            "confidence": "high" if max_similarity > 0.7 else "medium" if max_similarity > 0.6 else "low"
        }
    
    async def _detect_with_llm_fallback(self, content: str, fallback_model: Optional[str] = None, qa_feedback: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Detect OS using LLM via LMStudio (fallback)."""
        lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1")
        model_name = fallback_model or "mistralai/mistral-7b-instruct-v0.3"
        
        prompt = f"""Determine which operating system the described behaviors target (Windows, Linux, MacOS, or multiple). Output one label only.

Content:
{content[:3000]}

Output only the OS label: Windows, Linux, MacOS, or multiple"""
        
        try:
            # Mistral-7B-Instruct-v0.3 in LMStudio doesn't support system role
            # Combine system and user messages into a single user message
            combined_prompt = f"""You are a detection engineer. Determine which operating system the described behaviors target.

{prompt}"""
            
            # Add QA feedback if provided
            if qa_feedback:
                combined_prompt = f"{qa_feedback}\n\n{combined_prompt}"
            
            # Reasoning models (DeepSeek R1) need more tokens for reasoning output
            is_reasoning_model = 'deepseek-r1' in model_name.lower() or 'r1' in model_name.lower()
            max_tokens = 500 if is_reasoning_model else 50
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{lmstudio_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": combined_prompt
                            }
                        ],
                        "temperature": 0,
                        "max_tokens": max_tokens
                    }
                )
                
                if response.status_code != 200:
                    error_text = response.text[:500] if hasattr(response, 'text') else 'No error text'
                    logger.warning(f"LLM fallback failed: HTTP {response.status_code} - {error_text}")
                    return None
                
                result = response.json()
                if 'choices' not in result or len(result['choices']) == 0:
                    logger.warning(f"LLM fallback failed: No choices in response. Response keys: {list(result.keys())}")
                    return None
                
                # Handle reasoning models (DeepSeek R1) that return answer in reasoning_content
                message = result['choices'][0]['message']
                content_text = message.get('content', '')
                reasoning_text = message.get('reasoning_content', '')
                
                # For reasoning models, check reasoning_content first, then content
                if is_reasoning_model and reasoning_text:
                    response_text = reasoning_text.strip()
                else:
                    response_text = content_text.strip()
                
                # Parse response - look for OS label
                response_lower = response_text.lower()
                if "windows" in response_lower and "linux" not in response_lower and "macos" not in response_lower and "multiple" not in response_lower:
                    os_label = "Windows"
                elif "linux" in response_lower and "windows" not in response_lower and "macos" not in response_lower and "multiple" not in response_lower:
                    os_label = "Linux"
                elif "macos" in response_lower or "mac os" in response_lower:
                    os_label = "MacOS"
                elif "multiple" in response_lower:
                    os_label = "multiple"
                else:
                    os_label = "Unknown"
                
                return {
                    "operating_system": os_label,
                    "method": f"llm_fallback_{model_name}",
                    "raw_response": response_text[:200]
                }
        except Exception as e:
            logger.error(f"LLM fallback failed with exception: {type(e).__name__}: {e}", exc_info=True)
            return None
    
    async def detect_os(
        self,
        content: str,
        use_classifier: bool = True,
        use_fallback: bool = True,
        fallback_model: Optional[str] = None,
        force_fallback: bool = False,
        qa_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect OS from content.
        
        Args:
            content: Article content
            use_classifier: Try to use trained classifier first
            use_fallback: Fall back to LLM if classifier/similarity fails
            fallback_model: Optional LLM model name for fallback (defaults to mistralai/mistral-7b-instruct-v0.3)
            force_fallback: Always use LLM fallback regardless of confidence (for testing)
        
        Returns:
            Dict with operating_system, method, and confidence
        """
        # Try classifier first if available
        if use_classifier:
            result = self._detect_with_classifier(content)
            if result:
                return result
        
        # Fall back to similarity-based detection
        result = self._detect_with_similarity(content)
        
        # If force_fallback is enabled, always use LLM fallback
        if force_fallback and use_fallback:
            llm_result = await self._detect_with_llm_fallback(content, fallback_model=fallback_model, qa_feedback=qa_feedback)
            if llm_result:
                return llm_result
        
        # If similarity confidence is low and fallback is enabled, try LLM fallback
        if use_fallback and result.get("confidence") == "low":
            logger.info(f"Similarity confidence is low ({result.get('max_similarity', 'unknown')}), attempting LLM fallback...")
            llm_result = await self._detect_with_llm_fallback(content, fallback_model=fallback_model, qa_feedback=qa_feedback)
            if llm_result:
                logger.info(f"LLM fallback succeeded: {llm_result.get('operating_system')} (method: {llm_result.get('method')})")
                return llm_result
            else:
                logger.warning(f"LLM fallback failed or returned None, falling back to similarity result: {result.get('operating_system')}")
        
        return result
    
    def train_classifier(
        self,
        training_data: List[Dict[str, Any]],
        save_path: Optional[Path] = None
    ) -> Dict[str, Any]:
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
            content = item.get('content', '')
            os_label = item.get('os_label', 'Unknown')
            
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
        with open(save_path, 'wb') as f:
            pickle.dump(self.classifier, f)
        
        logger.info(f"Classifier trained and saved to {save_path}")
        
        # Calculate training metrics
        train_score = self.classifier.score(X, y)
        
        return {
            "training_samples": len(X),
            "train_accuracy": float(train_score),
            "classifier_type": self.classifier_type,
            "saved_path": str(save_path)
        }

