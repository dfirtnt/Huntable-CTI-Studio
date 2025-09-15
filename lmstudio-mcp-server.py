#!/usr/bin/env python3
"""
LMStudio MCP Server for CTIScraper
Provides programmatic access to LMStudio for high-performance LLM inference
"""

import json
import logging
import requests
import time
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LMStudio configuration
LMSTUDIO_BASE_URL = "http://localhost:1234"
LMSTUDIO_TIMEOUT = 30

class LMStudioMCPServer:
    def __init__(self):
        self.server = Server("lmstudio-mcp")
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available LMStudio tools"""
            tools = [
            Tool(
                name="lmstudio_chat",
                    description="Chat with LMStudio model for threat intelligence analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to send to the model"
                        },
                            "system_prompt": {
                            "type": "string",
                                "description": "System prompt for context",
                                "default": "You are a threat intelligence analyst specializing in SIGMA rule generation."
                        },
                        "max_tokens": {
                            "type": "integer",
                            "description": "Maximum tokens to generate",
                                "default": 200
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Sampling temperature",
                                "default": 0.7
                        }
                    },
                    "required": ["message"]
                }
            ),
            Tool(
                name="lmstudio_complete",
                    description="Complete text or code using LMStudio",
                inputSchema={
                    "type": "object",
                    "properties": {
                            "text": {
                            "type": "string",
                                "description": "Text to complete"
                        },
                        "max_tokens": {
                            "type": "integer",
                            "description": "Maximum tokens to generate",
                                "default": 100
                        }
                    },
                        "required": ["text"]
                }
            ),
            Tool(
                name="lmstudio_analyze_code",
                    description="Analyze code for security issues or performance",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to analyze"
                        },
                        "analysis_type": {
                            "type": "string",
                                "enum": ["security", "performance", "both"],
                                "description": "Type of analysis",
                            "default": "security"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="lmstudio_generate_tests",
                    description="Generate test cases for code",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to generate tests for"
                        },
                        "test_framework": {
                            "type": "string",
                            "description": "Test framework to use",
                            "default": "pytest"
                            }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="lmstudio_explain_code",
                    description="Explain code functionality",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to explain"
                        },
                        "detail_level": {
                            "type": "string",
                            "enum": ["brief", "detailed", "comprehensive"],
                                "description": "Level of detail",
                            "default": "detailed"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="lmstudio_refactor_code",
                    description="Refactor code for better performance or readability",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to refactor"
                        },
                        "refactor_type": {
                            "type": "string",
                                "enum": ["performance", "readability", "security", "all"],
                                "description": "Type of refactoring",
                                "default": "all"
                            }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="lmstudio_generate_docs",
                    description="Generate documentation for code",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to document"
                        },
                        "doc_type": {
                            "type": "string",
                                "enum": ["docstring", "readme", "api", "all"],
                                "description": "Type of documentation",
                            "default": "docstring"
                            }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="lmstudio_check_models",
                description="Check available models in LMStudio",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            )
        ]
            return ListToolsResult(tools=tools)

        @self.server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls"""
    try:
        if name == "lmstudio_chat":
                    result = await self._chat(
                        arguments.get("message", ""),
                        arguments.get("system_prompt", "You are a threat intelligence analyst specializing in SIGMA rule generation."),
                        arguments.get("max_tokens", 200),
                        arguments.get("temperature", 0.7)
                    )
        elif name == "lmstudio_complete":
                    result = await self._complete(
                        arguments.get("text", ""),
                        arguments.get("max_tokens", 100)
                    )
        elif name == "lmstudio_analyze_code":
                    result = await self._analyze_code(
                        arguments.get("code", ""),
                        arguments.get("analysis_type", "security")
                    )
        elif name == "lmstudio_generate_tests":
                    result = await self._generate_tests(
                        arguments.get("code", ""),
                        arguments.get("test_framework", "pytest")
                    )
        elif name == "lmstudio_explain_code":
                    result = await self._explain_code(
                        arguments.get("code", ""),
                        arguments.get("detail_level", "detailed")
                    )
        elif name == "lmstudio_refactor_code":
                    result = await self._refactor_code(
                        arguments.get("code", ""),
                        arguments.get("refactor_type", "all")
                    )
        elif name == "lmstudio_generate_docs":
                    result = await self._generate_docs(
                        arguments.get("code", ""),
                        arguments.get("doc_type", "docstring")
                    )
        elif name == "lmstudio_check_models":
                    result = await self._check_models()
        else:
                    result = f"Unknown tool: {name}"
                
                return CallToolResult(content=[TextContent(type="text", text=str(result))])
            
    except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])
    
    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make request to LMStudio API"""
        try:
            url = f"{LMSTUDIO_BASE_URL}{endpoint}"
            response = requests.post(url, json=data, timeout=LMSTUDIO_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"LMStudio API error: {str(e)}")
            raise Exception(f"LMStudio API error: {str(e)}")
    
    async def _chat(self, message: str, system_prompt: str, max_tokens: int, temperature: float) -> str:
        """Chat with LMStudio model"""
        data = {
            "model": "local-model",  # LMStudio uses this for local models
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "max_tokens": max_tokens,
                "temperature": temperature,
            "stream": False
        }
        
        result = await self._make_request("/v1/chat/completions", data)
        return result["choices"][0]["message"]["content"]
    
    async def _complete(self, text: str, max_tokens: int) -> str:
        """Complete text using LMStudio"""
        data = {
            "model": "local-model",
            "prompt": text,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        result = await self._make_request("/v1/completions", data)
        return result["choices"][0]["text"]
    
    async def _analyze_code(self, code: str, analysis_type: str) -> str:
        """Analyze code for security or performance issues"""
        prompt = f"Analyze the following code for {analysis_type} issues:\n\n```python\n{code}\n```\n\nProvide specific recommendations and potential vulnerabilities."
        
        return await self._chat(prompt, "You are a security and performance expert.", 300, 0.3)
    
    async def _generate_tests(self, code: str, test_framework: str) -> str:
        """Generate test cases for code"""
        prompt = f"Generate comprehensive {test_framework} test cases for the following code:\n\n```python\n{code}\n```\n\nInclude edge cases and error conditions."
        
        return await self._chat(prompt, "You are a testing expert.", 400, 0.5)
    
    async def _explain_code(self, code: str, detail_level: str) -> str:
        """Explain code functionality"""
        prompt = f"Explain the following code with {detail_level} detail:\n\n```python\n{code}\n```\n\nFocus on functionality, purpose, and key concepts."
        
        return await self._chat(prompt, "You are a software engineering expert.", 350, 0.4)
    
    async def _refactor_code(self, code: str, refactor_type: str) -> str:
        """Refactor code for improvement"""
        prompt = f"Refactor the following code for better {refactor_type}:\n\n```python\n{code}\n```\n\nProvide the refactored code with explanations."
        
        return await self._chat(prompt, "You are a code quality expert.", 400, 0.3)
    
    async def _generate_docs(self, code: str, doc_type: str) -> str:
        """Generate documentation for code"""
        prompt = f"Generate {doc_type} documentation for the following code:\n\n```python\n{code}\n```\n\nMake it clear and comprehensive."
        
        return await self._chat(prompt, "You are a technical writing expert.", 300, 0.4)
    
    async def _check_models(self) -> str:
    """Check available models in LMStudio"""
    try:
            response = requests.get(f"{LMSTUDIO_BASE_URL}/v1/models", timeout=10)
            if response.status_code == 200:
                models = response.json()
                return f"Available models: {json.dumps(models, indent=2)}"
        else:
                return f"Error checking models: HTTP {response.status_code}"
    except Exception as e:
            return f"Error checking models: {str(e)}"
    
    async def run(self):
        """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="lmstudio-mcp",
                server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                    notification_options=None,
                        experimental_capabilities={}
                    )
                )
        )

if __name__ == "__main__":
    import asyncio
    server = LMStudioMCPServer()
    asyncio.run(server.run())