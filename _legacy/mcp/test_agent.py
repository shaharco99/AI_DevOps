"""
Test script for MCP agent orchestration
"""
from __future__ import annotations

import asyncio

from agents import MCPAgentOrchestrator


async def test_agent():
    # Initialize agent
    agent = MCPAgentOrchestrator()

    # Add a simple test tool
    def echo(text: str) -> str:
        return f"Echo: {text}"

    agent.add_tool('echo', echo, 'Simply echoes back the text given to it')

    # Initialize and run a test query
    print('Running test query...')
    result = await agent.run('use the echo tool to say hello')
    print('\nResult:', result)

    return result['status'] == 'success'


if __name__ == '__main__':
    success = asyncio.run(test_agent())
    print('\nTest', 'passed' if success else 'failed')
