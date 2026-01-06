"""
Agent orchestration using LangChain + Ollama for MCP.
"""
from __future__ import annotations

from typing import Any, Dict, List

from langchain.agents import initialize_agent
from langchain.agents.types import AgentType
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool
from langchain_ollama import OllamaLLM


class MCPAgentOrchestrator:
    def __init__(self, base_url: str = 'http://localhost:11434'):
        """Initialize the agent orchestrator with Ollama."""
        self.llm = OllamaLLM(base_url=base_url, model='gpt-oss:latest', temperature=0)
        self.memory = ConversationBufferMemory(
            memory_key='chat_history', return_messages=True
        )
        self.tools: List[Tool] = []
        self.agent = None

    def add_tool(self, name: str, func: callable, description: str):
        """Add a tool that the agent can use."""
        self.tools.append(Tool(name=name, func=func, description=description))

    def initialize_agent(self):
        """Initialize the LangChain agent with tools."""
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            memory=self.memory,
            handle_parsing_errors=True,
            max_iterations=5,
            verbose=True,
        )

    async def run(self, query: str) -> Dict[str, Any]:
        """Run the agent with a query."""
        if not self.agent:
            self.initialize_agent()

        try:
            result = await self.agent.arun(query)
            return {'status': 'success', 'result': result, 'error': None}
        except Exception as e:
            return {'status': 'error', 'result': None, 'error': str(e)}

    def get_tools_description(self) -> List[Dict[str, str]]:
        """Get a list of available tools."""
        return [
            {'name': tool.name, 'description': tool.description} for tool in self.tools
        ]
