"""SimHash implementation for near-duplicate detection."""

import hashlib
from typing import List, Set, Tuple
import re
from collections import Counter


class SimHash:
    """SimHash implementation for detecting near-duplicate content."""
    
    def __init__(self, hash_bits: int = 64):
        self.hash_bits = hash_bits
        self.max_hash = 2 ** hash_bits - 1
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into features for SimHash."""
        # Convert to lowercase and split into words
        text = text.lower()
        # Remove punctuation and split
        tokens = re.findall(r'\b\w+\b', text)
        # Filter out very short tokens and common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those'
        }
        return [token for token in tokens if len(token) > 2 and token not in stop_words]
    
    def _get_feature_hash(self, feature: str) -> int:
        """Get hash value for a feature."""
        hash_obj = hashlib.md5(feature.encode('utf-8'))
        # Convert to integer and take modulo to fit in hash_bits
        return int(hash_obj.hexdigest(), 16) % (2 ** self.hash_bits)
    
    def _get_feature_vector(self, features: List[str]) -> List[int]:
        """Convert features to a vector of hash values."""
        return [self._get_feature_hash(feature) for feature in features]
    
    def _get_weighted_vector(self, features: List[str]) -> List[int]:
        """Get weighted vector based on feature frequency."""
        # Count feature frequencies
        feature_counts = Counter(features)
        
        # Initialize vector with zeros
        vector = [0] * self.hash_bits
        
        # Add weighted contributions for each feature
        for feature, count in feature_counts.items():
            feature_hash = self._get_feature_hash(feature)
            # Convert hash to binary and add weight
            for i in range(self.hash_bits):
                if feature_hash & (1 << i):
                    vector[i] += count
                else:
                    vector[i] -= count
        
        return vector
    
    def compute_simhash(self, text: str) -> int:
        """Compute SimHash for given text."""
        # Tokenize text
        features = self._tokenize(text)
        
        if not features:
            return 0
        
        # Get weighted vector
        vector = self._get_weighted_vector(features)
        
        # Convert to SimHash
        simhash = 0
        for i, weight in enumerate(vector):
            if weight > 0:
                simhash |= (1 << i)
        
        return simhash
    
    def compute_simhash_bucket(self, simhash: int, num_buckets: int = 16) -> int:
        """Compute bucket number for SimHash (for efficient lookup)."""
        return simhash % num_buckets
    
    def hamming_distance(self, simhash1: int, simhash2: int) -> int:
        """Calculate Hamming distance between two SimHashes."""
        xor_result = simhash1 ^ simhash2
        return bin(xor_result).count('1')
    
    def is_similar(self, simhash1: int, simhash2: int, threshold: int = 3) -> bool:
        """Check if two SimHashes are similar (within threshold)."""
        return self.hamming_distance(simhash1, simhash2) <= threshold
    
    def find_similar_hashes(self, target_simhash: int, simhash_list: List[int], threshold: int = 3) -> List[int]:
        """Find all SimHashes similar to target within threshold."""
        similar = []
        for simhash in simhash_list:
            if self.is_similar(target_simhash, simhash, threshold):
                similar.append(simhash)
        return similar


# Global SimHash instance
simhash_calculator = SimHash(hash_bits=64)


def compute_article_simhash(content: str, title: str = "") -> Tuple[int, int]:
    """Compute SimHash for article content and title."""
    # Combine content and title for SimHash calculation
    full_text = f"{title} {content}"
    simhash = simhash_calculator.compute_simhash(full_text)
    bucket = simhash_calculator.compute_simhash_bucket(simhash)
    return simhash, bucket


def is_content_similar(content1: str, content2: str, title1: str = "", title2: str = "", threshold: int = 3) -> bool:
    """Check if two articles have similar content."""
    simhash1, _ = compute_article_simhash(content1, title1)
    simhash2, _ = compute_article_simhash(content2, title2)
    return simhash_calculator.is_similar(simhash1, simhash2, threshold)
