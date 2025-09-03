"""
Test data generator utilities for CTI Scraper testing.
"""
import random
from typing import List, Dict, Any
from faker import Faker

fake = Faker()

class TestDataGenerator:
    """Generate test data for CTI Scraper testing."""
    
    @staticmethod
    def generate_article_data(count: int = 5) -> List[Dict[str, Any]]:
        """Generate test article data."""
        articles = []
        
        for i in range(count):
            article = {
                "id": i + 1,
                "title": fake.sentence(),
                "content": TestDataGenerator._generate_ttp_content(),
                "url": fake.url(),
                "source_id": random.randint(1, 3),
                "published_date": fake.date_time_this_year().isoformat(),
                "created_at": fake.date_time_this_year().isoformat(),
                "updated_at": fake.date_time_this_year().isoformat()
            }
            articles.append(article)
        
        return articles
    
    @staticmethod
    def generate_source_data(count: int = 3) -> List[Dict[str, Any]]:
        """Generate test source data."""
        sources = []
        
        source_names = ["Security Weekly", "Threat Post", "Dark Reading"]
        source_urls = [
            "https://securityweekly.com",
            "https://threatpost.com", 
            "https://darkreading.com"
        ]
        
        for i in range(count):
            source = {
                "id": i + 1,
                "name": source_names[i],
                "url": source_urls[i],
                "rss_url": f"{source_urls[i]}/feed.xml",
                "tier": random.randint(1, 3),
                "enabled": True,
                "categories": ["security", "threat-intel"],
                "total_articles": random.randint(50, 500),
                "success_rate": random.uniform(0.8, 1.0),
                "last_check": fake.date_time_this_month().isoformat(),
                "last_success": fake.date_time_this_month().isoformat()
            }
            sources.append(source)
        
        return sources
    
    @staticmethod
    def generate_ttp_analysis_data() -> Dict[str, Any]:
        """Generate test TTP analysis data."""
        techniques = [
            "T1055", "T1059", "T1071", "T1082", "T1105",
            "T1110", "T1114", "T1123", "T1132", "T1134"
        ]
        
        categories = ["MITRE ATT&CK", "Malware Techniques", "Social Engineering"]
        
        techniques_by_category = {}
        for category in categories:
            category_techniques = []
            for _ in range(random.randint(1, 3)):
                technique = {
                    "technique_name": random.choice(techniques),
                    "hunting_guidance": fake.sentence(),
                    "confidence": round(random.uniform(0.6, 1.0), 2),
                    "matched_text": fake.sentence()
                }
                category_techniques.append(technique)
            techniques_by_category[category] = category_techniques
        
        return {
            "total_techniques": sum(len(techs) for techs in techniques_by_category.values()),
            "overall_confidence": round(random.uniform(0.7, 0.95), 2),
            "hunting_priority": random.choice(["High", "Medium", "Low"]),
            "techniques_by_category": techniques_by_category
        }
    
    @staticmethod
    def generate_quality_assessment_data() -> Dict[str, Any]:
        """Generate test quality assessment data."""
        return {
            "ttp_score": random.randint(45, 75),
            "llm_score": random.randint(40, 80),
            "combined_score": random.uniform(50.0, 80.0),
            "quality_level": random.choice(["Excellent", "Good", "Fair", "Limited"]),
            "tactical_score": random.randint(60, 100),
            "strategic_score": random.randint(30, 80),
            "classification": random.choice(["Tactical", "Strategic", "Hybrid"]),
            "hunting_priority": random.choice(["High", "Medium", "Low"]),
            "structure_score": random.randint(15, 25),
            "technical_score": random.randint(12, 25),
            "intelligence_score": random.randint(18, 25),
            "recommendations": [
                fake.sentence(),
                fake.sentence()
            ]
        }
    
    @staticmethod
    def _generate_ttp_content() -> str:
        """Generate content with TTP indicators."""
        ttp_indicators = [
            "process injection", "command and control", "lateral movement",
            "credential harvesting", "data exfiltration", "persistence",
            "privilege escalation", "defense evasion", "initial access"
        ]
        
        paragraphs = []
        for _ in range(random.randint(3, 6)):
            paragraph = fake.paragraph()
            # Add TTP indicators randomly
            if random.random() < 0.7:
                indicator = random.choice(ttp_indicators)
                paragraph += f" The attacker used {indicator} techniques."
            paragraphs.append(paragraph)
        
        return " ".join(paragraphs)
    
    @staticmethod
    def generate_database_stats() -> Dict[str, Any]:
        """Generate test database statistics."""
        return {
            "total_articles": random.randint(100, 1000),
            "total_sources": random.randint(3, 10),
            "last_update": fake.date_time_this_month().isoformat(),
            "articles_today": random.randint(5, 50),
            "sources_active": random.randint(2, 8)
        }

class MockResponse:
    """Mock HTTP response for testing."""
    
    def __init__(self, status_code: int = 200, content: str = "", headers: Dict = None):
        self.status_code = status_code
        self.content = content.encode() if isinstance(content, str) else content
        self.text = content if isinstance(content, str) else content.decode()
        self.headers = headers or {}
    
    def json(self):
        """Return JSON content if available."""
        import json
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def raise_for_status(self):
        """Raise HTTPError for bad status codes."""
        if self.status_code >= 400:
            from httpx import HTTPStatusError
            raise HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)

def create_mock_article(id: int = 1) -> Dict[str, Any]:
    """Create a single mock article."""
    return {
        "id": id,
        "title": f"Test Article {id}",
        "content": f"This is test content for article {id} with TTP indicators like process injection and command and control.",
        "url": f"https://example.com/article-{id}",
        "source_id": 1,
        "published_date": "2024-01-01T00:00:00",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00"
    }

def create_mock_source(id: int = 1) -> Dict[str, Any]:
    """Create a single mock source."""
    return {
        "id": id,
        "name": f"Test Source {id}",
        "url": f"https://testsource{id}.com",
        "rss_url": f"https://testsource{id}.com/feed.xml",
        "tier": 1,
        "enabled": True,
        "categories": ["security", "threat-intel"],
        "total_articles": 100,
        "success_rate": 0.95,
        "last_check": "2024-01-01T00:00:00",
        "last_success": "2024-01-01T00:00:00"
    }
