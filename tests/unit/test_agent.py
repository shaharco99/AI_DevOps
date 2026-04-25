"""Unit tests for AI agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_devops_assistant.agents.agent import DevOpsAgent


class TestDevOpsAgent:
    """Test DevOps agent."""

    @pytest.fixture
    def agent(self):
        """Agent fixture."""
        return DevOpsAgent()

    @pytest.mark.asyncio
    async def test_chat_basic_response(self, agent):
        """Test basic chat response."""
        with patch("ai_devops_assistant.agents.agent.get_ollama_service") as mock_llm, patch(
            "ai_devops_assistant.agents.agent.get_tool_executor"
        ) as mock_executor, patch(
            "ai_devops_assistant.agents.agent.get_session_manager"
        ) as mock_session:
            # Mock LLM service
            mock_llm_instance = AsyncMock()
            mock_llm_instance.generate_response.return_value = (
                "Hello, I can help with DevOps tasks!"
            )
            mock_llm_instance.health_check.return_value = True
            mock_llm_instance.chat.return_value = "Hello, I can help with DevOps tasks!"
            mock_llm.return_value = mock_llm_instance

            # Mock tool executor
            mock_executor_instance = MagicMock()
            mock_executor_instance.should_use_tools.return_value = False
            mock_executor.return_value = mock_executor_instance

            # Mock session manager
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            # Initialize agent
            await agent.initialize()

            response = await agent.chat("Hello", "test_session")

            assert "Hello, I can help with DevOps tasks!" in response["message"]

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, agent):
        """Test chat with tool usage."""
        with patch("ai_devops_assistant.agents.agent.get_ollama_service") as mock_llm, patch(
            "ai_devops_assistant.agents.agent.get_tool_executor"
        ) as mock_executor, patch(
            "ai_devops_assistant.agents.agent.get_session_manager"
        ) as mock_session:
            # Mock LLM service - response contains tool call JSON
            tool_response = """I'll check the logs for you.

```json
{
  "tools": [
    {"name": "log_analysis_tool", "parameters": {"query": "error logs"}}
  ]
}
```"""
            mock_llm_instance = AsyncMock()
            mock_llm_instance.health_check.return_value = True
            mock_llm_instance.chat.side_effect = [tool_response, "Found 5 error logs in the system"]
            mock_llm.return_value = mock_llm_instance

            # Mock tool executor
            mock_executor_instance = MagicMock()
            mock_executor_instance.execute_tool.return_value = "Found 5 error logs"
            mock_executor.return_value = mock_executor_instance

            # Mock session manager
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            # Initialize agent
            await agent.initialize()

            response = await agent.chat("Check error logs", "test_session")

            assert "Found 5 error logs in the system" in response["message"]
            assert len(response["tool_calls"]) > 0

    @pytest.mark.asyncio
    async def test_chat_error_handling(self, agent):
        """Test error handling in chat."""
        with patch("ai_devops_assistant.agents.agent.get_ollama_service") as mock_llm, patch(
            "ai_devops_assistant.agents.agent.get_tool_executor"
        ) as mock_executor, patch(
            "ai_devops_assistant.agents.agent.get_session_manager"
        ) as mock_session:
            # Mock LLM service to raise exception
            mock_llm_instance = AsyncMock()
            mock_llm_instance.generate_response.side_effect = Exception("LLM error")
            mock_llm_instance.health_check.return_value = True
            mock_llm_instance.chat.side_effect = Exception("LLM error")
            mock_llm.return_value = mock_llm_instance

            # Mock tool executor
            mock_executor_instance = MagicMock()
            mock_executor_instance.should_use_tools.return_value = False
            mock_executor.return_value = mock_executor_instance

            # Mock session manager
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance

            # Initialize agent
            await agent.initialize()

            response = await agent.chat("Hello", "test_session")

            assert "error" in response["message"].lower() or "sorry" in response["message"].lower()
