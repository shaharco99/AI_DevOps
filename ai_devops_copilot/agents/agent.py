"""Main LangChain-based DevOps agent."""

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_copilot.agents.memory import ConversationMemory, get_session_manager
from ai_devops_copilot.agents.prompts import SYSTEM_PROMPT
from ai_devops_copilot.config.settings import settings
from ai_devops_copilot.rag.retriever import get_rag_retriever
from ai_devops_copilot.services.llm_service import get_ollama_service
from ai_devops_copilot.tools.tool_executor import get_tool_executor

logger = logging.getLogger(__name__)


class DevOpsAgent:
    """AI DevOps Agent orchestrator."""

    def __init__(self, session: Optional[AsyncSession] = None):
        """Initialize agent.
        
        Args:
            session: SQLAlchemy async session for database tools
        """
        self.llm_service = None
        self.tool_executor = get_tool_executor(session)
        self.rag_retriever = get_rag_retriever() if settings.ENABLE_RAG else None
        self.session_manager = get_session_manager()
        self.session = session

    async def initialize(self) -> None:
        """Initialize agent components."""
        try:
            self.llm_service = await get_ollama_service()
            if not await self.llm_service.health_check():
                logger.warning("LLM service not available, agent may have limited functionality")
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        use_rag: bool = True,
    ) -> dict[str, Any]:
        """Process user message and generate response.
        
        Args:
            message: User message
            session_id: Optional session ID for multi-turn conversations
            use_rag: Whether to use RAG for knowledge retrieval
            
        Returns:
            dict: Response with message, tool calls, and metadata
        """
        try:
            # Get or create session
            if session_id:
                memory = self.session_manager.get_or_create_session(session_id)
            else:
                memory = ConversationMemory()

            # Add user message to memory
            memory.add_message("user", message)

            # Step 1: Determine if RAG retrieval is needed
            rag_context = ""
            if use_rag and self.rag_retriever:
                rag_context = await self._retrieve_rag_context(message)

            # Step 2: Build context for LLM
            system_context = self._build_system_context(memory, rag_context)

            # Step 3: Call LLM to determine tools and get response
            if not self.llm_service:
                return self._error_response("LLM service not available", memory)

            # Prepare conversation history for LLM
            messages = self._format_messages_for_llm(memory, message)

            # Get LLM response
            llm_response = await self.llm_service.chat(messages)

            # Parse tool calls from response if any
            tool_calls, tool_results = await self._execute_tool_calls(llm_response, message)

            # If tools were used, ask LLM to synthesize results
            final_response = llm_response
            if tool_results:
                synthesis_prompt = self._build_synthesis_prompt(
                    message, tool_results
                )
                final_messages = messages + [
                    {"role": "assistant", "content": llm_response},
                    {"role": "user", "content": synthesis_prompt},
                ]
                final_response = await self.llm_service.chat(final_messages)

            # Add assistant message to memory
            memory.add_message("assistant", final_response, {"tools_used": tool_calls})

            return {
                "success": True,
                "message": final_response,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
                "session_id": session_id,
                "metadata": {
                    "used_rag": bool(rag_context),
                    "tools_available": len(self.tool_executor.get_available_tools()),
                },
            }

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return self._error_response(str(e), memory if 'memory' in locals() else None)

    async def _retrieve_rag_context(self, query: str) -> str:
        """Retrieve context from RAG system."""
        try:
            documents = self.rag_retriever.retrieve(query)
            context = self.rag_retriever.format_context(documents)
            return context
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return ""

    def _build_system_context(self, memory: ConversationMemory, rag_context: str) -> str:
        """Build system context for LLM."""
        context_parts = [SYSTEM_PROMPT]

        if rag_context:
            context_parts.append(f"\nRelevant Knowledge Base:\n{rag_context[:2000]}")

        available_tools = self.tool_executor.get_available_tools()
        if available_tools:
            context_parts.append("\nAvailable Tools:")
            for tool_name, description in available_tools.items():
                context_parts.append(f"- {tool_name}: {description}")

        return "\n".join(context_parts)

    def _format_messages_for_llm(self, memory: ConversationMemory, current_message: str) -> list[dict]:
        """Format conversation history for LLM."""
        messages = []

        # Add system message
        messages.append({
            "role": "system",
            "content": SYSTEM_PROMPT,
        })

        # Add previous messages from memory
        for msg in memory.get_last_n_messages(6):  # Keep last 6 messages
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        return messages

    async def _execute_tool_calls(
        self,
        llm_response: str,
        user_query: str,
    ) -> tuple[list[dict], dict[str, Any]]:
        """Extract and execute tool calls from LLM response.
        
        Returns:
            tuple: (tool_calls, tool_results)
        """
        tool_calls = []
        tool_results = {}

        # Try to parse JSON tool calls from response
        try:
            # Simple heuristic: look for JSON blocks in response
            if "```json" in llm_response:
                json_start = llm_response.find("```json") + 7
                json_end = llm_response.find("```", json_start)
                json_str = llm_response[json_start:json_end].strip()
                tool_data = json.loads(json_str)

                # Execute tools
                if isinstance(tool_data, dict) and "tools" in tool_data:
                    for tool_call in tool_data["tools"]:
                        tool_name = tool_call.get("name")
                        params = tool_call.get("parameters", {})

                        result = await self.tool_executor.execute_tool(tool_name, **params)
                        tool_calls.append({"name": tool_name, "parameters": params})
                        tool_results[tool_name] = result

        except (json.JSONDecodeError, ValueError, IndexError):
            # No valid tool calls found, that's okay
            pass

        return tool_calls, tool_results

    def _build_synthesis_prompt(
        self,
        user_query: str,
        tool_results: dict[str, Any],
    ) -> str:
        """Build synthesis prompt for final response."""
        results_text = "\n".join(
            f"- {tool_name}: {result}"
            for tool_name, result in tool_results.items()
        )

        return f"""Based on the tool results below, provide a comprehensive answer to the user's question.

User Question: {user_query}

Tool Results:
{results_text}

Please synthesize these results into a clear, actionable response."""

    def _error_response(self, error: str, memory: Optional[ConversationMemory] = None) -> dict[str, Any]:
        """Build error response."""
        return {
            "success": False,
            "message": f"Error: {error}",
            "tool_calls": [],
            "tool_results": {},
            "session_id": None,
        }


# Global agent instance
_agent: Optional[DevOpsAgent] = None


async def get_agent(session: Optional[AsyncSession] = None) -> DevOpsAgent:
    """Get or create DevOps agent.
    
    Args:
        session: Optional database session
        
    Returns:
        DevOpsAgent: Agent instance
    """
    global _agent
    if _agent is None:
        _agent = DevOpsAgent(session)
        await _agent.initialize()
    return _agent
