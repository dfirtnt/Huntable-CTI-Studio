#!/usr/bin/env python3
"""Score OS detection performance using SEC-BERT embeddings with similarity-based classification."""

import sys
import os
import subprocess
import json
import re
from collections import defaultdict
from typing import Dict, Any, Optional, List
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from sklearn.metrics.pairwise import cosine_similarity

# Load OSDetectionAgent prompt for reference
OS_DETECTION_PROMPT_PATH = "src/prompts/OSDetectionAgent"
if not os.path.exists(OS_DETECTION_PROMPT_PATH):
    print(f"Error: OSDetectionAgent prompt not found at {OS_DETECTION_PROMPT_PATH}")
    sys.exit(1)

with open(OS_DETECTION_PROMPT_PATH, 'r') as f:
    prompt_config_dict = json.load(f)

# SEC-BERT model name - can be overridden via environment variable
SECBERT_MODEL = os.getenv("SECBERT_MODEL", "e3b/security-bert")  # Default, may need adjustment

RESULTS_FILE = "secbert_os_detection_scores.json"

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple"]

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
    ]
}

class SECBERTOSDetector:
    """OS detection using SEC-BERT embeddings."""
    
    def __init__(self, model_name: str = None, use_gpu: bool = True):
        """Initialize SEC-BERT model."""
        self.model_name = model_name or SECBERT_MODEL
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        self.tokenizer = None
        self.model = None
        self._model_loaded = False
        self.os_indicator_embeddings = {}
        
    def _load_model(self):
        """Load SEC-BERT model and tokenizer."""
        if self._model_loaded:
            return
        
        try:
            print(f"Loading SEC-BERT model: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name)
            self.model.eval()
            
            if self.device >= 0:
                self.model = self.model.to(f"cuda:{self.device}")
            
            self._model_loaded = True
            print(f"Successfully loaded SEC-BERT model on device {self.device}")
            
            # Pre-compute OS indicator embeddings
            self._precompute_os_embeddings()
            
        except Exception as e:
            print(f"Failed to load SEC-BERT model: {e}")
            print(f"Trying alternative model names...")
            # Try common alternatives
            alternatives = [
                "e3b/security-bert",
                "ehsanaghaei/SecureBERT",
                "security-bert",
                "SecBERT"
            ]
            for alt_model in alternatives:
                if alt_model == self.model_name:
                    continue
                try:
                    print(f"Trying: {alt_model}")
                    self.model_name = alt_model
                    self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                    self.model = AutoModel.from_pretrained(self.model_name)
                    self.model.eval()
                    
                    if self.device >= 0:
                        self.model = self.model.to(f"cuda:{self.device}")
                    
                    self._model_loaded = True
                    print(f"Successfully loaded SEC-BERT model '{alt_model}' on device {self.device}")
                    self._precompute_os_embeddings()
                    return
                except Exception as e2:
                    print(f"  Failed: {e2}")
                    continue
            
            raise RuntimeError(f"Could not load SEC-BERT model. Tried: {self.model_name} and alternatives")
    
    def _get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text using SEC-BERT."""
        if not self._model_loaded:
            self._load_model()
        
        # Tokenize and encode
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
        print("Pre-computing OS indicator embeddings...")
        for os_name, indicators in OS_INDICATORS.items():
            # Combine all indicators for this OS
            combined_text = " ".join(indicators)
            embedding = self._get_embedding(combined_text)
            self.os_indicator_embeddings[os_name] = embedding
        print("OS indicator embeddings computed")
    
    def detect_os(self, content: str) -> Dict[str, Any]:
        """
        Detect OS from content using SEC-BERT embeddings.
        
        Returns:
            Dict with 'operating_system' and similarity scores
        """
        if not self._model_loaded:
            self._load_model()
        
        # Generate embedding for article content (truncate to 512 tokens worth)
        # Use first 2000 chars as representative sample
        content_sample = content[:2000]
        content_embedding = self._get_embedding(content_sample)
        
        # Calculate similarity to each OS
        similarities = {}
        for os_name, os_embedding in self.os_indicator_embeddings.items():
            similarity = cosine_similarity(
                content_embedding.reshape(1, -1),
                os_embedding.reshape(1, -1)
            )[0][0]
            similarities[os_name] = float(similarity)
        
        # Determine OS based on similarities
        max_similarity = max(similarities.values())
        max_os = max(similarities, key=similarities.get)
        
        # If multiple OSes have high similarity (>0.7), classify as "multiple"
        high_similarity_oses = [os for os, sim in similarities.items() if sim > 0.7]
        
        if len(high_similarity_oses) > 1:
            detected_os = "multiple"
        elif max_similarity > 0.6:
            detected_os = max_os
        else:
            # Low confidence - default to multiple
            detected_os = "multiple"
        
        return {
            "operating_system": detected_os,
            "similarities": similarities,
            "max_similarity": float(max_similarity),
            "confidence": "high" if max_similarity > 0.7 else "medium" if max_similarity > 0.6 else "low"
        }

def evaluate_detection(result: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate OS detection quality and return metrics."""
    metrics = {
        'json_valid': True,  # Always valid for SEC-BERT (not JSON-based)
        'has_operating_system': False,
        'operating_system': None,
        'is_valid_label': False,
        'confidence': None,
        'max_similarity': None,
        'error': None
    }
    
    if not result:
        metrics['error'] = 'No result to evaluate'
        return metrics
    
    if 'operating_system' in result:
        metrics['has_operating_system'] = True
        os_label = result['operating_system']
        if isinstance(os_label, str):
            metrics['operating_system'] = os_label
            metrics['is_valid_label'] = os_label in VALID_OS_LABELS
            if not metrics['is_valid_label']:
                metrics['error'] = f'Invalid OS label: {os_label}. Must be one of {VALID_OS_LABELS}'
        else:
            metrics['error'] = f'operating_system is not a string: {type(os_label)}'
    else:
        metrics['error'] = 'Missing operating_system field'
    
    if 'confidence' in result:
        metrics['confidence'] = result['confidence']
    if 'max_similarity' in result:
        metrics['max_similarity'] = result['max_similarity']
    
    return metrics

def detect_os_from_article(article_id: int, title: str, source: str, url: str, content: str) -> Optional[Dict[str, Any]]:
    """Detect OS from a single article using SEC-BERT."""
    try:
        detector = SECBERTOSDetector()
        result = detector.detect_os(content)
        
        result['article_id'] = article_id
        result['title'] = title
        result['url'] = url
        
        return result
    except Exception as e:
        print(f"Article {article_id}: Error: {e}")
        return None

def load_results():
    """Load previous results from file."""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return defaultdict(list)

def save_results(results):
    """Save results to file."""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(dict(results), f, indent=2)

def main():
    """Main function to detect OS from all articles."""
    article_ids = [1974, 1909, 1866, 1860, 1937, 1794]
    
    # Fetch article data from database
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-F", "|", "-c", 
         f"SELECT a.id, a.title, a.canonical_url, s.name, a.content FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id IN ({','.join(map(str, article_ids))}) ORDER BY id;"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Database query failed: {result.stderr}")
        return
    
    articles = []
    for line in result.stdout.strip().split('\n'):
        if not line or '|' not in line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            articles.append({
                'id': int(parts[0]),
                'title': parts[1],
                'url': parts[2],
                'source': parts[3],
                'content': parts[4]
            })
    
    print(f"Detecting OS from {len(articles)} articles with SEC-BERT...\n")
    
    # Detect OS from all articles
    all_results = load_results()
    
    for article in articles:
        print(f"Processing article {article['id']}...")
        result = detect_os_from_article(
            article_id=article['id'],
            title=article['title'],
            source=article['source'],
            url=article['url'],
            content=article['content']
        )
        
        if result:
            metrics = evaluate_detection(result)
            os_label = metrics['operating_system']
            
            article_id = result['article_id']
            if str(article_id) not in all_results:
                all_results[str(article_id)] = []
            
            all_results[str(article_id)].append({
                'operating_system': os_label,
                'is_valid_label': metrics['is_valid_label'],
                'confidence': metrics.get('confidence'),
                'max_similarity': metrics.get('max_similarity'),
                'similarities': result.get('similarities', {}),
                'metrics': metrics
            })
            
            print(f"  ✓ Article {article_id}: OS = {os_label}, Confidence = {metrics.get('confidence')}, Similarity = {metrics.get('max_similarity', 0):.3f}")
        else:
            print(f"  ✗ Article {article['id']}: Failed")
    
    save_results(all_results)
    
    print("\n" + "-" * 80)
    print("Results Summary:")
    print("-" * 80)
    for article_id in sorted([int(k) for k in all_results.keys()]):
        runs = all_results[str(article_id)]
        if runs:
            os_labels = [r['operating_system'] for r in runs]
            confidences = [r.get('confidence', 'unknown') for r in runs]
            similarities = [r.get('max_similarity', 0) for r in runs]
            print(f"Article {article_id}: OS = {os_labels[0]}, Confidence = {confidences[0]}, Similarity = {similarities[0]:.3f}")

if __name__ == "__main__":
    main()

