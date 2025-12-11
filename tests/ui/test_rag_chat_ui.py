"""
UI tests for RAG chat interface.
"""
import json
import re
import pytest
from playwright.sync_api import Page, expect


class TestRAGChatUI:
    """Test RAG chat UI functionality."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    def test_chat_page_loads(self, page: Page):
        """Test that the chat page loads correctly."""
        page.goto("http://localhost:8001/chat")
        page.wait_for_load_state("networkidle")
        
        # Check page title and main elements
        expect(page).to_have_title(re.compile(r"RAG Chat - Huntable .* Studio"))
        
        # Check for main chat interface elements
        expect(page.locator("h2")).to_contain_text("Threat Intelligence Chat")
        expect(page.locator("textarea[placeholder*='Ask about cybersecurity']")).to_be_visible()
        expect(page.locator("button:has-text('Send')")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_interface_elements(self, page: Page):
        """Test that all chat interface elements are present."""
        page.goto("http://localhost:8001/chat")
        
        # Check header elements
        expect(page.locator("h2")).to_contain_text("Threat Intelligence Chat")
        
        # Check parameter controls
        expect(page.locator("label:has-text('Max Results:')")).to_be_visible()
        expect(page.locator("select#maxResults")).to_be_visible()
        expect(page.locator("label:has-text('Similarity:')")).to_be_visible()
        expect(page.locator("select#threshold")).to_be_visible()
        
        # Check input area
        expect(page.locator("textarea[placeholder*='Ask about cybersecurity']")).to_be_visible()
        expect(page.locator("button:has-text('Send')")).to_be_visible()
        
        # Check footer
        expect(page.locator("text=Try asking:")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_parameter_controls(self, page: Page):
        """Test chat parameter controls functionality."""
        page.goto("http://localhost:8001/chat")
        
        # Test max results dropdown
        max_results_select = page.locator("select#maxResults")
        expect(max_results_select).to_be_visible()
        expect(max_results_select).to_have_value("5")
        
        # Change max results
        max_results_select.select_option("10")
        expect(max_results_select).to_have_value("10")
        
        # Test similarity threshold dropdown
        threshold_select = page.locator("select#threshold")
        expect(threshold_select).to_be_visible()
        expect(threshold_select).to_have_value("0.4")
        
        # Change threshold
        threshold_select.select_option("0.5")
        expect(threshold_select).to_have_value("0.5")
    
    @pytest.mark.ui
    def test_chat_input_functionality(self, page: Page):
        """Test chat input functionality."""
        page.goto("http://localhost:8001/chat")
        
        # Test input field
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        expect(input_field).to_be_visible()
        expect(input_field).to_be_enabled()
        
        # Test typing in input
        input_field.fill("What are the latest cybersecurity threats?")
        expect(input_field).to_have_value("What are the latest cybersecurity threats?")
        
        # Test send button
        send_button = page.locator("button:has-text('Send')")
        expect(send_button).to_be_visible()
        expect(send_button).to_be_enabled()
    
    @pytest.mark.ui
    @pytest.mark.smoke
    def test_chat_send_smoke(self, page: Page):
        """Smoke: sending a prompt renders without errors."""
        page.goto("http://localhost:8001/chat")
        page.wait_for_load_state("networkidle")

        prompt = "smoke check prompt"
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        send_button = page.locator("button:has-text('Send')")

        expect(input_field).to_be_visible()

        input_field.fill(prompt)
        if send_button.is_enabled():
            send_button.click()
            expect(page.locator(f"text={prompt}")).to_be_visible()
        else:
            pytest.skip("Send button disabled (likely missing chat configuration)")

        # UI stays interactive (no error overlays)
        page.wait_for_timeout(1500)
        expect(input_field).to_be_visible()

    @pytest.mark.ui
    def test_chat_message_sending(self, page: Page):
        """Test sending chat messages."""
        page.goto("http://localhost:8001/chat")
        
        # Wait for initial greeting message
        expect(page.locator("text=Hello! I'm your threat intelligence assistant")).to_be_visible()
        
        # Send a message
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        input_field.fill("What are ransomware threats?")
        
        send_button = page.locator("button:has-text('Send')")
        send_button.click()
        
        # Check that message appears in chat
        expect(page.locator("text=What are ransomware threats?")).to_be_visible()
        
        # Check for loading indicator
        expect(page.locator("text=Thinking...")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_message_history(self, page: Page):
        """Test chat message history display."""
        page.goto("http://localhost:8001/chat")
        
        # Wait for initial message
        expect(page.locator("text=Hello! I'm your threat intelligence assistant")).to_be_visible()
        
        # Send multiple messages
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        
        # First message
        input_field.fill("Tell me about malware")
        page.locator("button:has-text('Send')").click()
        
        # Wait for response
        page.wait_for_timeout(2000)
        
        # Second message
        input_field.fill("What about ransomware?")
        page.locator("button:has-text('Send')").click()
        
        # Check that both messages are in history
        expect(page.locator("text=Tell me about malware")).to_be_visible()
        expect(page.locator("text=What about ransomware?")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_response_display(self, page: Page):
        """Test chat response display."""
        page.goto("http://localhost:8001/chat")
        
        # Send a message
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        input_field.fill("cybersecurity threats")
        page.locator("button:has-text('Send')").click()
        
        # Wait for response
        page.wait_for_timeout(3000)
        
        # Check that response is displayed
        # Note: This test assumes the API is working and returns a response
        # In a real test environment, you might want to mock the API response
        expect(page.locator("text=Thinking...")).not_to_be_visible()
        
        # Check for response content (if API is working)
        # expect(page.locator("text=threat intelligence")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_article_links(self, page: Page):
        """Test that article links in chat responses are clickable."""
        page.goto("http://localhost:8001/chat")
        
        # Send a message
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        input_field.fill("cybersecurity threats")
        page.locator("button:has-text('Send')").click()
        
        # Wait for response
        page.wait_for_timeout(3000)
        
        # Check for article links (if any are returned)
        # Note: This test assumes articles are returned with clickable links
        # In a real test environment, you might want to mock the API response
        article_links = page.locator("a[href*='/articles/']")
        
        if article_links.count() > 0:
            # Test that links are clickable
            first_link = article_links.first
            expect(first_link).to_be_visible()
            expect(first_link).to_be_enabled()
            
            # Test clicking on a link opens new tab
            with page.context.expect_page() as new_page:
                first_link.click()
            
            new_page = new_page.value
            expect(new_page).to_have_url(lambda url: "articles/" in url)
            new_page.close()
    
    @pytest.mark.ui
    def test_chat_error_handling(self, page: Page):
        """Test chat error handling."""
        page.goto("http://localhost:8001/chat")
        
        # Mock API failure
        page.route("**/api/chat/rag", lambda route: route.abort())
        
        # Send a message
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        input_field.fill("test message")
        page.locator("button:has-text('Send')").click()
        
        # Wait for error response
        page.wait_for_timeout(2000)
        
        # Check for error message
        expect(page.locator("text=Error:")).to_be_visible()
        expect(page.locator("text=Could not connect")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_empty_message_validation(self, page: Page):
        """Test chat empty message validation."""
        page.goto("http://localhost:8001/chat")
        
        # Try to send empty message
        send_button = page.locator("button:has-text('Send')")
        send_button.click()
        
        # Check that no new message is added
        # The input should remain empty and no new message should appear
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        expect(input_field).to_have_value("")
    
    @pytest.mark.ui
    def test_chat_loading_state(self, page: Page):
        """Test chat loading state."""
        page.goto("http://localhost:8001/chat")
        
        # Send a message
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        input_field.fill("test message")
        
        # Check that input is disabled during loading
        page.locator("button:has-text('Send')").click()
        
        # Check for loading indicator
        expect(page.locator("text=Thinking...")).to_be_visible()
        
        # Check that input is disabled
        expect(input_field).to_be_disabled()
        expect(page.locator("button:has-text('Send')")).to_be_disabled()
    
    @pytest.mark.ui
    def test_chat_scroll_behavior(self, page: Page):
        """Test chat scroll behavior."""
        page.goto("http://localhost:8001/chat")
        
        # Send multiple messages to create scrollable content
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        
        for i in range(5):
            input_field.fill(f"Test message {i}")
            page.locator("button:has-text('Send')").click()
            page.wait_for_timeout(1000)
        
        # Check that chat scrolls to bottom
        # Note: This is a basic test - in a real environment you might want to
        # check actual scroll position
        expect(page.locator("text=Test message 4")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_responsive_design(self, page: Page):
        """Test chat responsive design."""
        page.goto("http://localhost:8001/chat")
        
        # Test desktop view
        page.set_viewport_size({"width": 1280, "height": 720})
        expect(page.locator("h2")).to_be_visible()
        expect(page.locator("input[placeholder*='cybersecurity']")).to_be_visible()
        
        # Test mobile view
        page.set_viewport_size({"width": 375, "height": 667})
        expect(page.locator("h2")).to_be_visible()
        expect(page.locator("input[placeholder*='cybersecurity']")).to_be_visible()
        
        # Test tablet view
        page.set_viewport_size({"width": 768, "height": 1024})
        expect(page.locator("h2")).to_be_visible()
        expect(page.locator("input[placeholder*='cybersecurity']")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_accessibility(self, page: Page):
        """Test chat accessibility features."""
        page.goto("http://localhost:8001/chat")
        
        # Check for proper labels
        expect(page.locator("label[for='maxResults']")).to_be_visible()
        expect(page.locator("label[for='threshold']")).to_be_visible()
        
        # Check for proper input attributes
        input_field = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        expect(input_field).to_have_attribute("rows", "2")
        
        # Check for proper button attributes
        send_button = page.locator("button:has-text('Send')")
        expect(send_button).to_have_attribute("type", "submit")
        
        # Check keyboard navigation
        input_field.focus()
        expect(input_field).to_be_focused()
        
        # Test Enter key submission
        input_field.fill("test message")
        input_field.press("Enter")
        expect(page.locator("text=test message")).to_be_visible()
    
    @pytest.mark.ui
    def test_chat_navigation_integration(self, page: Page):
        """Test chat navigation integration."""
        page.goto("http://localhost:8001/")
        
        # Check that chat link exists in navigation
        chat_link = page.locator("a[href='/chat']")
        expect(chat_link).to_be_visible()
        expect(chat_link).to_contain_text("Chat")
        
        # Navigate to chat page
        chat_link.click()
        expect(page).to_have_url("http://localhost:8001/chat")
        
        # Check that chat page loads
        expect(page.locator("h2")).to_contain_text("Threat Intelligence Chat")
        
        # Navigate back to dashboard
        dashboard_link = page.locator("a[href='/']")
        dashboard_link.click()
        expect(page).to_have_url("http://localhost:8001/")

    @pytest.mark.ui
    def test_chat_displays_selected_model_name(self, page: Page):
        """Ensure the LLM model badge matches the settings selection."""
        page.add_init_script(
            "window.localStorage.setItem('ctiScraperSettings', JSON.stringify({aiModel: 'chatgpt'}));"
        )

        captured_request = {}

        def handle_chat_route(route):
            request_body = json.loads(route.request.post_data or "{}")
            captured_request["llm_provider"] = request_body.get("llm_provider")

            mock_response = {
                "response": "Test response from mocked provider.",
                "timestamp": "2025-01-01T00:00:00Z",
                "relevant_articles": [],
                "total_results": 0,
                "query": request_body.get("message"),
                "llm_provider": "openai",
                "llm_model_name": "OpenAI • gpt-4o-mini",
                "use_llm_generation": True,
            }

            route.fulfill(
                status=200,
                body=json.dumps(mock_response),
                headers={"Content-Type": "application/json"},
            )

        page.route("**/api/chat/rag", handle_chat_route)
        page.goto("http://localhost:8001/chat")

        page.locator("textarea[placeholder*='Ask about cybersecurity']").fill("Model check?")
        page.locator("button:has-text('Send')").click()

        expect(page.locator("text=Model check?")).to_be_visible()
        expect(page.locator("text=🤖 OpenAI • gpt-4o-mini")).to_be_visible()
        assert captured_request.get("llm_provider") == "chatgpt"
