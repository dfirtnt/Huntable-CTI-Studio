#!/usr/bin/env python3
"""
Simple Web Server Test Suite for CTI Scraper
Tests all major endpoints and functionality
"""

import requests
import time
import json
from typing import Dict, List

class WebServerTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = {}
        
    def test_endpoint(self, endpoint: str, expected_status: int = 200, method: str = "GET", **kwargs) -> bool:
        """Test a single endpoint and return success status"""
        try:
            url = f"{self.base_url}{endpoint}"
            print(f"Testing {method} {url}")
            
            if method.upper() == "GET":
                response = self.session.get(url, **kwargs)
            elif method.upper() == "POST":
                response = self.session.post(url, **kwargs)
            else:
                print(f"❌ Unsupported method: {method}")
                return False
            
            success = response.status_code == expected_status
            status_icon = "✅" if success else "❌"
            print(f"{status_icon} {endpoint}: {response.status_code} (expected: {expected_status})")
            
            if not success:
                print(f"   Response: {response.text[:200]}...")
            
            return success
            
        except Exception as e:
            print(f"❌ {endpoint}: Error - {str(e)}")
            return False
    
    def test_dashboard(self) -> bool:
        """Test the main dashboard"""
        print("\n🏠 Testing Dashboard...")
        success = self.test_endpoint("/")
        
        if success:
            # Test that dashboard loads with expected content
            response = self.session.get(f"{self.base_url}/")
            content = response.text.lower()
            
            # Check for key dashboard elements
            checks = [
                ("dashboard title", "cti scraper" in content),
                ("articles section", "recent articles" in content or "articles" in content),
                ("sources section", "sources" in content),
                ("stats section", "statistics" in content or "total articles" in content)
            ]
            
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"   {status} {check_name}")
                success = success and check_result
        
        self.test_results['dashboard'] = success
        return success
    
    def test_articles_list(self) -> bool:
        """Test the articles listing page"""
        print("\n📰 Testing Articles List...")
        success = self.test_endpoint("/articles")
        
        if success:
            # Test pagination
            success = success and self.test_endpoint("/articles?page=1&per_page=10")
            
            # Test search functionality
            success = success and self.test_endpoint("/articles?search=threat")
            
            # Test source filtering
            response = self.session.get(f"{self.base_url}/articles")
            if response.status_code == 200:
                content = response.text.lower()
                checks = [
                    ("articles table", "article" in content),
                    ("pagination", "page" in content or "next" in content),
                    ("search form", "search" in content)
                ]
                
                for check_name, check_result in checks:
                    status = "✅" if check_result else "❌"
                    print(f"   {status} {check_name}")
                    success = success and check_result
        
        self.test_results['articles_list'] = success
        return success
    
    def test_article_detail(self) -> bool:
        """Test individual article detail pages"""
        print("\n📄 Testing Article Detail Pages...")
        
        # First get a list of articles to test individual pages
        response = self.session.get(f"{self.base_url}/articles")
        if response.status_code != 200:
            print("❌ Cannot test article details - articles list failed")
            self.test_results['article_detail'] = False
            return False
        
        # Look for article IDs in the response
        content = response.text
        import re
        article_links = re.findall(r'/articles/(\d+)', content)
        
        if not article_links:
            print("❌ No article links found")
            self.test_results['article_detail'] = False
            return False
        
        # Test the first few articles
        test_articles = article_links[:3]
        success = True
        
        for article_id in test_articles:
            article_success = self.test_endpoint(f"/articles/{article_id}")
            success = success and article_success
            
            if article_success:
                # Check for quality assessment section
                response = self.session.get(f"{self.base_url}/articles/{article_id}")
                content = response.text.lower()
                
                quality_checks = [
                    ("quality assessment", "quality assessment" in content),
                    ("ttp analysis", "ttp analysis" in content or "hunting techniques" in content),
                    ("article content", "article content" in content)
                ]
                
                for check_name, check_result in quality_checks:
                    status = "✅" if check_result else "❌"
                    print(f"   {status} {check_name} (Article {article_id})")
        
        self.test_results['article_detail'] = success
        return success
    
    def test_analysis_dashboard(self) -> bool:
        """Test the TTP analysis dashboard"""
        print("\n🔍 Testing TTP Analysis Dashboard...")
        success = self.test_endpoint("/analysis")
        
        if success:
            response = self.session.get(f"{self.base_url}/analysis")
            content = response.text.lower()
            
            checks = [
                ("analysis title", "ttp analysis" in content or "analysis" in content),
                ("quality metrics", "quality" in content or "score" in content),
                ("technique breakdown", "technique" in content or "category" in content)
            ]
            
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"   {status} {check_name}")
                success = success and check_result
        
        self.test_results['analysis_dashboard'] = success
        return success
    
    def test_sources_page(self) -> bool:
        """Test the sources management page"""
        print("\n⚙️ Testing Sources Page...")
        success = self.test_endpoint("/sources")
        
        if success:
            response = self.session.get(f"{self.base_url}/sources")
            content = response.text.lower()
            
            checks = [
                ("sources title", "sources" in content),
                ("source list", "source" in content),
                ("status information", "status" in content or "active" in content)
            ]
            
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"   {status} {check_name}")
                success = success and check_result
        
        self.test_results['sources_page'] = success
        return success
    
    def test_api_endpoints(self) -> bool:
        """Test the JSON API endpoints"""
        print("\n🔌 Testing API Endpoints...")
        
        # Test articles API
        api_success = self.test_endpoint("/api/articles")
        api_success = api_success and self.test_endpoint("/api/articles?page=1&per_page=5")
        
        # Test article analysis API
        response = self.session.get(f"{self.base_url}/articles")
        if response.status_code == 200:
            import re
            article_links = re.findall(r'/articles/(\d+)', response.text)
            if article_links:
                api_success = api_success and self.test_endpoint(f"/api/analysis/{article_links[0]}")
        
        self.test_results['api_endpoints'] = api_success
        return api_success
    
    def test_error_handling(self) -> bool:
        """Test error handling for invalid requests"""
        print("\n⚠️ Testing Error Handling...")
        
        # Test 404 for non-existent article
        error_success = self.test_endpoint("/articles/99999", expected_status=404)
        
        # Test 404 for non-existent page
        error_success = error_success and self.test_endpoint("/nonexistent", expected_status=404)
        
        self.test_results['error_handling'] = error_success
        return error_success
    
    def test_performance(self) -> bool:
        """Test basic performance metrics"""
        print("\n⚡ Testing Performance...")
        
        endpoints = ["/", "/articles", "/analysis", "/sources"]
        response_times = {}
        
        for endpoint in endpoints:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}{endpoint}")
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000  # Convert to milliseconds
            response_times[endpoint] = response_time
            
            status = "✅" if response.status_code == 200 else "❌"
            print(f"   {status} {endpoint}: {response_time:.1f}ms")
        
        # Check if response times are reasonable (< 2 seconds)
        reasonable_times = all(time < 2000 for time in response_times.values())
        
        if reasonable_times:
            print("   ✅ All endpoints respond within reasonable time")
        else:
            print("   ⚠️ Some endpoints are slow")
        
        self.test_results['performance'] = reasonable_times
        return reasonable_times
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all tests and return results"""
        print("🧪 Starting CTI Scraper Web Server Tests...")
        print("=" * 60)
        
        # Run all test categories
        self.test_dashboard()
        self.test_articles_list()
        self.test_article_detail()
        self.test_analysis_dashboard()
        self.test_sources_page()
        self.test_api_endpoints()
        self.test_error_handling()
        self.test_performance()
        
        return self.test_results
    
    def print_summary(self):
        """Print a summary of all test results"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDetailed Results:")
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status} {test_name.replace('_', ' ').title()}")
        
        if failed_tests == 0:
            print("\n🎉 All tests passed! Your web server is working perfectly!")
        else:
            print(f"\n⚠️ {failed_tests} test(s) failed. Check the details above.")
        
        return failed_tests == 0

def main():
    """Main test runner"""
    # Check if server is running
    try:
        response = requests.get("http://localhost:8000", timeout=5)
        if response.status_code != 200:
            print("❌ Web server is not responding properly")
            return False
    except requests.exceptions.RequestException:
        print("❌ Web server is not running. Please start it first:")
        print("   ./start_web.sh")
        return False
    
    # Run tests
    tester = WebServerTester()
    results = tester.run_all_tests()
    
    # Print summary
    all_passed = tester.print_summary()
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
