#!/usr/bin/env python3
"""
Simple Web Server Monitor for CTI Scraper
Monitors server health and provides quick status checks
"""

import requests
import time
import json
from datetime import datetime

class WebServerMonitor:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def check_server_status(self) -> dict:
        """Check overall server health"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'server_running': False,
            'response_time': None,
            'endpoints': {},
            'database_stats': None,
            'overall_health': 'unknown'
        }
        
        try:
            # Check if server is responding
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/", timeout=5)
            end_time = time.time()
            
            status['server_running'] = response.status_code == 200
            status['response_time'] = round((end_time - start_time) * 1000, 1)  # ms
            
            if status['server_running']:
                # Check key endpoints
                endpoints_to_check = ['/articles', '/analysis', '/sources']
                for endpoint in endpoints_to_check:
                    try:
                        ep_response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
                        status['endpoints'][endpoint] = {
                            'status': ep_response.status_code,
                            'healthy': ep_response.status_code == 200
                        }
                    except Exception as e:
                        status['endpoints'][endpoint] = {
                            'status': 'error',
                            'healthy': False,
                            'error': str(e)
                        }
                
                # Try to get database stats from dashboard
                try:
                    dashboard_response = self.session.get(f"{self.base_url}/")
                    if dashboard_response.status_code == 200:
                        content = dashboard_response.text.lower()
                        if 'total articles' in content and 'sources' in content:
                            status['database_stats'] = 'accessible'
                        else:
                            status['database_stats'] = 'partial'
                    else:
                        status['database_stats'] = 'error'
                except Exception:
                    status['database_stats'] = 'error'
                
                # Determine overall health
                healthy_endpoints = sum(1 for ep in status['endpoints'].values() if ep['healthy'])
                total_endpoints = len(status['endpoints'])
                
                if healthy_endpoints == total_endpoints and status['database_stats'] == 'accessible':
                    status['overall_health'] = 'excellent'
                elif healthy_endpoints >= total_endpoints * 0.8:
                    status['overall_health'] = 'good'
                elif healthy_endpoints >= total_endpoints * 0.5:
                    status['overall_health'] = 'fair'
                else:
                    status['overall_health'] = 'poor'
                    
        except Exception as e:
            status['error'] = str(e)
            status['overall_health'] = 'down'
        
        return status
    
    def print_status(self, status: dict):
        """Print a formatted status report"""
        print(f"\n🖥️  CTI Scraper Web Server Status")
        print(f"⏰  {status['timestamp']}")
        print("=" * 50)
        
        # Server status
        if status['server_running']:
            print(f"✅ Server: RUNNING")
            print(f"⚡ Response Time: {status['response_time']}ms")
        else:
            print(f"❌ Server: DOWN")
            if 'error' in status:
                print(f"   Error: {status['error']}")
            return
        
        # Endpoint health
        print(f"\n🔗 Endpoint Health:")
        for endpoint, ep_status in status['endpoints'].items():
            icon = "✅" if ep_status['healthy'] else "❌"
            status_text = "HEALTHY" if ep_status['healthy'] else f"ERROR ({ep_status['status']})"
            print(f"   {icon} {endpoint}: {status_text}")
        
        # Database status
        if status['database_stats']:
            db_icon = "✅" if status['database_stats'] == 'accessible' else "⚠️"
            print(f"\n🗄️  Database: {db_icon} {status['database_stats'].upper()}")
        
        # Overall health
        health_icons = {
            'excellent': '🟢',
            'good': '🟡', 
            'fair': '🟠',
            'poor': '🔴',
            'down': '⚫',
            'unknown': '⚪'
        }
        
        health_icon = health_icons.get(status['overall_health'], '⚪')
        print(f"\n🏥 Overall Health: {health_icon} {status['overall_health'].upper()}")
    
    def quick_check(self):
        """Quick health check with minimal output"""
        status = self.check_server_status()
        
        if status['overall_health'] == 'excellent':
            print("✅ Web server is healthy and running perfectly!")
        elif status['overall_health'] in ['good', 'fair']:
            print("⚠️  Web server is running with minor issues")
        elif status['overall_health'] == 'poor':
            print("❌ Web server has significant issues")
        else:
            print("💀 Web server is down")
        
        return status['overall_health'] in ['excellent', 'good']

def main():
    """Main monitoring function"""
    monitor = WebServerMonitor()
    
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
    
    # Run comprehensive status check
    status = monitor.check_server_status()
    monitor.print_status(status)
    
    return status['overall_health'] in ['excellent', 'good']

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
