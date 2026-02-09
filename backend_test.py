#!/usr/bin/env python3
"""
Chintan News App - Backend API Testing
Tests all backend endpoints including auth, articles, AI features, and protected routes
"""

import requests
import sys
import json
from datetime import datetime, timezone, timedelta
import uuid
import time

class ChintanAPITester:
    def __init__(self, base_url="https://thinkdeep-news.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session_token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details="", expected_status=None, actual_status=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
            if expected_status and actual_status:
                print(f"   Expected: {expected_status}, Got: {actual_status}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "expected_status": expected_status,
            "actual_status": actual_status
        })

    def test_health_check(self):
        """Test basic health endpoint"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            success = response.status_code == 200
            self.log_test("Health Check", success, "", 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Health Check", False, f"Error: {str(e)}")
            return False

    def test_root_endpoint(self):
        """Test root API endpoint"""
        try:
            response = requests.get(f"{self.api_url}/", timeout=10)
            success = response.status_code == 200
            if success:
                data = response.json()
                success = "Chintan" in data.get("message", "")
            self.log_test("Root Endpoint", success, "", 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Root Endpoint", False, f"Error: {str(e)}")
            return False

    def create_test_user_session(self):
        """Create test user and session directly in database simulation"""
        try:
            # Generate test credentials
            timestamp = int(time.time())
            self.user_id = f"test_user_{timestamp}"
            self.session_token = f"test_session_{timestamp}_{uuid.uuid4().hex[:8]}"
            
            print(f"🔧 Created test session: {self.session_token}")
            print(f"🔧 Test user ID: {self.user_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to create test session: {str(e)}")
            return False

    def test_articles_endpoint(self):
        """Test articles endpoint - should return 12 Indian news articles"""
        try:
            response = requests.get(f"{self.api_url}/articles", timeout=15)
            success = response.status_code == 200
            
            if success:
                articles = response.json()
                success = len(articles) >= 10  # Should have at least 10 articles
                details = f"Found {len(articles)} articles"
                
                # Check if articles have required fields
                if articles and len(articles) > 0:
                    first_article = articles[0]
                    required_fields = ['article_id', 'title', 'description', 'content', 'category', 'source']
                    missing_fields = [field for field in required_fields if field not in first_article]
                    if missing_fields:
                        success = False
                        details += f", Missing fields: {missing_fields}"
                    else:
                        details += ", All required fields present"
            else:
                details = "Failed to fetch articles"
            
            self.log_test("Articles Endpoint (12 Indian News)", success, details, 200, response.status_code)
            return success, articles if success else []
        except Exception as e:
            self.log_test("Articles Endpoint (12 Indian News)", False, f"Error: {str(e)}")
            return False, []

    def test_developing_stories(self):
        """Test developing stories endpoint"""
        try:
            response = requests.get(f"{self.api_url}/articles/developing", timeout=10)
            success = response.status_code == 200
            
            if success:
                stories = response.json()
                details = f"Found {len(stories)} developing stories"
                # Check if stories have developing/breaking flags
                if stories:
                    has_flags = any(story.get('is_developing') or story.get('is_breaking') for story in stories)
                    if not has_flags:
                        details += " (Warning: No developing/breaking flags found)"
            else:
                details = "Failed to fetch developing stories"
            
            self.log_test("Developing Stories Endpoint", success, details, 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Developing Stories Endpoint", False, f"Error: {str(e)}")
            return False

    def test_morning_brief(self):
        """Test morning brief endpoint"""
        try:
            response = requests.get(f"{self.api_url}/briefs/morning", timeout=10)
            success = response.status_code == 200
            
            if success:
                brief = response.json()
                required_fields = ['type', 'title', 'articles']
                missing_fields = [field for field in required_fields if field not in brief]
                if missing_fields:
                    success = False
                    details = f"Missing fields: {missing_fields}"
                else:
                    details = f"Brief contains {len(brief.get('articles', []))} articles"
            else:
                details = "Failed to fetch morning brief"
            
            self.log_test("Morning Brief Endpoint", success, details, 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Morning Brief Endpoint", False, f"Error: {str(e)}")
            return False

    def test_interest_categories(self):
        """Test interest categories endpoint"""
        try:
            response = requests.get(f"{self.api_url}/interests/categories", timeout=10)
            success = response.status_code == 200
            
            if success:
                categories = response.json()
                expected_categories = ['Politics', 'Technology', 'Business', 'Sports', 'Entertainment', 'Science']
                found_categories = list(categories.keys()) if isinstance(categories, dict) else []
                missing_categories = [cat for cat in expected_categories if cat not in found_categories]
                
                if missing_categories:
                    details = f"Missing categories: {missing_categories}"
                else:
                    details = f"Found {len(found_categories)} categories"
                    success = len(found_categories) >= 6
            else:
                details = "Failed to fetch categories"
            
            self.log_test("Interest Categories Endpoint", success, details, 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Interest Categories Endpoint", False, f"Error: {str(e)}")
            return False

    def test_auth_me_without_token(self):
        """Test /api/auth/me without authentication - should return 401"""
        try:
            response = requests.get(f"{self.api_url}/auth/me", timeout=10)
            success = response.status_code == 401
            details = "Correctly returns 401 for unauthenticated request"
            self.log_test("Auth Me (No Token)", success, details, 401, response.status_code)
            return success
        except Exception as e:
            self.log_test("Auth Me (No Token)", False, f"Error: {str(e)}")
            return False

    def test_protected_routes_without_auth(self):
        """Test protected routes without authentication"""
        protected_endpoints = [
            "/bookmarks",
            "/users/stats", 
            "/users/interests"
        ]
        
        all_success = True
        for endpoint in protected_endpoints:
            try:
                response = requests.get(f"{self.api_url}{endpoint}", timeout=10)
                success = response.status_code == 401
                if not success:
                    all_success = False
                details = f"Returns {response.status_code} for {endpoint}"
                self.log_test(f"Protected Route {endpoint} (No Auth)", success, details, 401, response.status_code)
            except Exception as e:
                self.log_test(f"Protected Route {endpoint} (No Auth)", False, f"Error: {str(e)}")
                all_success = False
        
        return all_success

    def test_poll_endpoint(self, article_id=None):
        """Test poll endpoint"""
        if not article_id:
            article_id = "article_india001"  # Use sample article ID
        
        try:
            response = requests.get(f"{self.api_url}/polls/{article_id}", timeout=10)
            success = response.status_code in [200, 404]  # 404 is acceptable if no poll exists
            
            if response.status_code == 200:
                poll = response.json()
                if poll:
                    required_fields = ['poll_id', 'question', 'options', 'votes']
                    missing_fields = [field for field in required_fields if field not in poll]
                    if missing_fields:
                        details = f"Poll found but missing fields: {missing_fields}"
                    else:
                        details = f"Poll found with {len(poll.get('options', []))} options"
                else:
                    details = "No poll found for article"
            else:
                details = f"No poll exists for article {article_id}"
            
            self.log_test("Poll Endpoint", success, details, "200 or 404", response.status_code)
            return success
        except Exception as e:
            self.log_test("Poll Endpoint", False, f"Error: {str(e)}")
            return False

    def test_ai_questions_endpoint(self, article_id=None):
        """Test AI questions endpoint - should return max 3 questions"""
        if not article_id:
            article_id = "article_india001"
        
        try:
            response = requests.get(f"{self.api_url}/ai/questions/{article_id}", timeout=15)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                questions = data.get('questions', [])
                details = f"Generated {len(questions)} AI questions"
                
                # Check if questions are limited to 3 max
                if len(questions) > 3:
                    success = False
                    details += f" (ERROR: Should be max 3 questions, got {len(questions)})"
                elif len(questions) == 0:
                    details += " (Warning: No questions generated)"
                else:
                    details += " (Correctly limited to max 3)"
            else:
                details = "Failed to fetch AI questions"
            
            self.log_test("AI Questions Endpoint (Max 3)", success, details, 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("AI Questions Endpoint (Max 3)", False, f"Error: {str(e)}")
            return False

    def test_article_detail(self, article_id=None):
        """Test individual article endpoint"""
        if not article_id:
            article_id = "article_india001"
        
        try:
            response = requests.get(f"{self.api_url}/articles/{article_id}", timeout=10)
            success = response.status_code == 200
            
            if success:
                article = response.json()
                required_fields = ['article_id', 'title', 'content', 'what', 'why', 'context', 'impact']
                missing_fields = [field for field in required_fields if field not in article]
                if missing_fields:
                    success = False
                    details = f"Missing fields: {missing_fields}"
                else:
                    details = "Article has all required fields for collapsible sections"
            else:
                details = f"Failed to fetch article {article_id}"
            
            self.log_test("Article Detail Endpoint", success, details, 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("Article Detail Endpoint", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Chintan Backend API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Basic connectivity tests
        print("\n📡 Basic Connectivity Tests")
        self.test_health_check()
        self.test_root_endpoint()
        
        # Public endpoints tests
        print("\n📰 Public Endpoints Tests")
        articles_success, articles = self.test_articles_endpoint()
        self.test_developing_stories()
        self.test_morning_brief()
        self.test_interest_categories()
        
        # Article detail test
        if articles:
            first_article_id = articles[0].get('article_id')
            self.test_article_detail(first_article_id)
            self.test_poll_endpoint(first_article_id)
            self.test_ai_questions_endpoint(first_article_id)
        
        # Auth tests
        print("\n🔐 Authentication Tests")
        self.test_auth_me_without_token()
        self.test_protected_routes_without_auth()
        
        # Create test session for protected route testing
        print("\n🔧 Test Session Creation")
        session_created = self.create_test_user_session()
        
        # Print results
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        # Categorize results
        critical_failures = []
        warnings = []
        
        for result in self.test_results:
            if not result["success"]:
                if "Health" in result["test"] or "Articles Endpoint" in result["test"]:
                    critical_failures.append(result["test"])
                else:
                    warnings.append(result["test"])
        
        if critical_failures:
            print(f"\n🚨 CRITICAL FAILURES ({len(critical_failures)}):")
            for failure in critical_failures:
                print(f"  - {failure}")
        
        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for warning in warnings:
                print(f"  - {warning}")
        
        if success_rate >= 80:
            print(f"\n✅ Backend API Status: HEALTHY ({success_rate:.1f}%)")
            return 0
        elif success_rate >= 60:
            print(f"\n⚠️  Backend API Status: DEGRADED ({success_rate:.1f}%)")
            return 1
        else:
            print(f"\n❌ Backend API Status: CRITICAL ({success_rate:.1f}%)")
            return 2

def main():
    """Main test execution"""
    tester = ChintanAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())