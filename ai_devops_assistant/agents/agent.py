"""Advanced AI Agent Framework for DevOps operations."""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.agents.memory import ConversationMemory, get_session_manager
from ai_devops_assistant.agents.prompts import SYSTEM_PROMPT
from ai_devops_assistant.observability.ai_observability import (
    observability_manager, trace_context
)
from ai_devops_assistant.services.llm_service import get_ollama_service
from ai_devops_assistant.tools.tool_executor import get_tool_executor

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent specialization roles."""
    GENERAL = "general"
    DEVOPS = "devops"
    SECURITY = "security"
    MONITORING = "monitoring"
    DATABASE = "database"
    INFRASTRUCTURE = "infrastructure"


class AgentCapability(Enum):
    """Agent capabilities."""
    TOOL_USE = "tool_use"
    RAG_RETRIEVAL = "rag_retrieval"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    EXECUTION = "execution"


@dataclass
class AgentConfig:
    """Configuration for an AI agent."""
    role: AgentRole = AgentRole.GENERAL
    capabilities: List[AgentCapability] = field(default_factory=lambda: [
        AgentCapability.TOOL_USE,
        AgentCapability.RAG_RETRIEVAL,
        AgentCapability.PLANNING,
    ])
    model_name: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: Optional[str] = None
    tool_allowlist: Optional[List[str]] = None
    max_tool_iterations: int = 5
    enable_planning: bool = True
    enable_reflection: bool = True


@dataclass
class AgentTask:
    """Represents a task for an agent to execute."""
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 1
    requires_tools: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class AgentResponse:
    """Response from an agent execution."""
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    reasoning_steps: List[str] = field(default_factory=list)


class ToolCall:
    """Represents a tool call made by an agent."""

    def __init__(self, tool_name: str, parameters: Dict[str, Any]):
        self.tool_name = tool_name
        self.parameters = parameters
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.execution_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
        }


class DevOpsAgent:
    """Advanced AI DevOps Agent with tool use and multi-agent capabilities."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        session: Optional[AsyncSession] = None
    ):
        """Initialize agent.

        Args:
            config: Agent configuration
            session: SQLAlchemy async session for database tools
        """
        self.config = config or AgentConfig()
        self.llm_service = None
        self.tool_executor = get_tool_executor(session)
        self.rag_pipeline = None
        self.session_manager = get_session_manager()
        self.session = session
        self.conversation_memory: Optional[ConversationMemory] = None

        # Agent state
        self.current_task: Optional[AgentTask] = None
        self.execution_history: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        """Initialize agent components."""
        try:
            self.llm_service = await get_ollama_service()
            if not await self.llm_service.health_check():
                logger.warning("LLM service not available, agent may have limited functionality")

            # Initialize RAG if capability enabled
            if AgentCapability.RAG_RETRIEVAL in self.config.capabilities:
                try:
                    from ai_devops_assistant.rag.pipeline import RAGPipeline
                    self.rag_pipeline = RAGPipeline()
                    await self.rag_pipeline.initialize()
                except Exception as e:
                    logger.warning(f"RAG pipeline not available: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        use_rag: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Process user message and generate response with advanced agent capabilities.

        Args:
            message: User input message
            session_id: Conversation session ID
            use_rag: Whether to use RAG for context
            **kwargs: Additional parameters

        Returns:
            Response dictionary with content, metadata, and tool calls
        """
        with trace_context("agent_chat", agent_role=self.config.role.value):
            try:
                # Initialize conversation memory if needed
                if session_id and not self.conversation_memory:
                    self.conversation_memory = self.session_manager.get_or_create_session(session_id)

                # Create task for this interaction
                task = AgentTask(description=message, context={"session_id": session_id})

                # Execute task
                response = await self._execute_task(task, use_rag=use_rag)

                # Update conversation memory
                if self.conversation_memory:
                    self.conversation_memory.add_message("user", message)
                    self.conversation_memory.add_message("assistant", response.content)

                # Record execution
                self.execution_history.append({
                    "timestamp": asyncio.get_event_loop().time(),
                    "task": task.description,
                    "response": response.content,
                    "tool_calls": len(response.tool_calls),
                    "confidence": response.confidence_score,
                })

                return {
                    "content": response.content,
                    "message": response.content,
                    "tool_calls": [call.to_dict() for call in response.tool_calls],
                    "metadata": response.metadata,
                    "confidence_score": response.confidence_score,
                    "reasoning_steps": response.reasoning_steps,
                    "session_id": session_id,
                }

            except Exception as e:
                logger.error(f"Agent chat failed: {e}", exc_info=True)
                return {
                    "content": f"I apologize, but I encountered an error: {str(e)}",
                    "message": f"I apologize, but I encountered an error: {str(e)}",
                    "error": str(e),
                    "tool_calls": [],
                    "metadata": {},
                    "confidence_score": 0.0,
                    "reasoning_steps": [],
                }

    async def _execute_task(self, task: AgentTask, use_rag: bool = True) -> AgentResponse:
        """Execute a task using agent capabilities."""
        task.status = "running"
        reasoning_steps = []

        try:
            # Step 1: Gather context
            context = await self._gather_context(task, use_rag)
            reasoning_steps.append("Gathered relevant context from knowledge base")

            # Step 2: Plan execution (if planning enabled)
            if self.config.enable_planning and AgentCapability.PLANNING in self.config.capabilities:
                plan = await self._create_execution_plan(task, context)
                reasoning_steps.append(f"Created execution plan with {len(plan)} steps")
            else:
                plan = [{"action": "direct_response", "reasoning": "Simple query - direct response"}]

            # Step 3: Execute plan
            response_content = ""
            tool_calls = []

            for step in plan:
                if step["action"] == "tool_call":
                    # Execute tool
                    tool_call = await self._execute_tool_call(step)
                    tool_calls.append(tool_call)
                    reasoning_steps.append(f"Executed tool: {tool_call.tool_name}")

                    # Incorporate tool result into context
                    context += f"\nTool result ({tool_call.tool_name}): {tool_call.result}"

                elif step["action"] == "reasoning":
                    # Generate reasoning step
                    reasoning = await self._generate_reasoning_step(context, step)
                    reasoning_steps.append(reasoning)
                    context += f"\nReasoning: {reasoning}"

            # Step 4: Generate final response
            final_response = await self._generate_final_response(task, context, tool_calls)
            reasoning_steps.append("Generated final response incorporating all context")

            # Calculate confidence
            confidence = self._calculate_confidence(tool_calls, reasoning_steps)

            task.status = "completed"
            task.result = final_response

            return AgentResponse(
                content=final_response,
                tool_calls=tool_calls,
                metadata={
                    "task_id": task.id,
                    "execution_plan": plan,
                    "context_sources": len(context.split("\n")) if context else 0,
                },
                confidence_score=confidence,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            raise

    async def _gather_context(self, task: AgentTask, use_rag: bool) -> str:
        """Gather relevant context for task execution."""
        context_parts = []

        # Add conversation history if available
        if self.conversation_memory:
            history = self.conversation_memory.get_last_n_messages(5)
            if history:
                context_parts.append("Recent conversation:")
                for msg in history[-3:]:  # Last 3 messages for context
                    context_parts.append(f"{msg['role']}: {msg['content']}")

        # Add RAG context if enabled
        if use_rag and self.rag_pipeline and AgentCapability.RAG_RETRIEVAL in self.config.capabilities:
            try:
                rag_result = await self.rag_pipeline.query(task.description, top_k=3)
                if rag_result.documents:
                    context_parts.append("Relevant knowledge:")
                    for doc in rag_result.documents:
                        context_parts.append(f"Context: {doc.content[:500]}...")
            except Exception as e:
                logger.warning(f"RAG context gathering failed: {e}")

        # Add role-specific context
        role_context = self._get_role_context()
        if role_context:
            context_parts.append(f"Role context ({self.config.role.value}): {role_context}")

        return "\n".join(context_parts)

    async def _create_execution_plan(self, task: AgentTask, context: str) -> List[Dict[str, Any]]:
        """Create an execution plan for the task."""
        planning_prompt = f"""
        Analyze this task and create a step-by-step execution plan.
        Task: {task.description}
        Context: {context[:1000]}

        Available tools: {list(self.tool_executor.get_available_tools().keys())}
        Agent capabilities: {[cap.value for cap in self.config.capabilities]}

        Return a JSON array of steps, where each step has:
        - "action": "tool_call", "reasoning", or "direct_response"
        - "tool_name": (if tool_call)
        - "parameters": (if tool_call)
        - "reasoning": explanation of why this step

        Focus on being efficient and using tools only when necessary.
        """

        try:
            response = await observability_manager.trace_llm_call(
                provider="ollama",
                model=self.config.model_name,
                prompt=planning_prompt,
                call_fn=lambda: self.llm_service.chat([
                    {"role": "user", "content": planning_prompt}
                ])
            )

            # Parse JSON response
            plan_text = response.strip()
            match = re.search(r"```json\s*(.*?)```", plan_text, re.S)
            if match:
                plan_text = match.group(1).strip()
            if plan_text.startswith("```json"):
                plan_text = plan_text[7:]
            if plan_text.endswith("```"):
                plan_text = plan_text[:-3]

            plan = json.loads(plan_text)
            if isinstance(plan, dict) and "tools" in plan:
                return [
                    {
                        "action": "tool_call",
                        "tool_name": tool.get("name"),
                        "parameters": tool.get("parameters", {}),
                    }
                    for tool in plan["tools"]
                ]
            return plan if isinstance(plan, list) else [plan]

        except Exception as e:
            logger.warning(f"Planning failed, using simple approach: {e}")
            return [{"action": "direct_response", "reasoning": "Planning failed - direct response"}]

    async def _execute_tool_call(self, step: Dict[str, Any]) -> ToolCall:
        """Execute a tool call."""
        tool_name = step.get("tool_name")
        parameters = step.get("parameters", {})

        if not tool_name:
            raise ValueError("Tool call missing tool_name")

        # Check tool allowlist
        if self.config.tool_allowlist and tool_name not in self.config.tool_allowlist:
            raise ValueError(f"Tool {tool_name} not in allowlist")

        tool_call = ToolCall(tool_name, parameters)

        try:
            # Execute tool
            import time
            start_time = time.time()

            result = await self.tool_executor.execute_tool(tool_name, **parameters)

            tool_call.execution_time = time.time() - start_time
            tool_call.result = result

        except Exception as e:
            tool_call.error = str(e)
            logger.error(f"Tool execution failed: {tool_name} - {e}")

        return tool_call

    async def _generate_reasoning_step(self, context: str, step: Dict[str, Any]) -> str:
        """Generate a reasoning step."""
        reasoning_prompt = f"""
        Based on the current context, provide reasoning for the next step.

        Context: {context[:1500]}
        Step: {step}

        Provide concise reasoning (1-2 sentences) explaining this step's purpose.
        """

        try:
            response = await observability_manager.trace_llm_call(
                provider="ollama",
                model=self.config.model_name,
                prompt=reasoning_prompt,
                call_fn=lambda: self.llm_service.chat([
                    {"role": "user", "content": reasoning_prompt}
                ])
            )
            return response.strip()
        except Exception as e:
            return f"Reasoning step: {step.get('reasoning', 'Unknown purpose')}"

    async def _generate_final_response(
        self,
        task: AgentTask,
        context: str,
        tool_calls: List[ToolCall]
    ) -> str:
        """Generate the final response incorporating all context and tool results."""
        # Build comprehensive prompt
        system_prompt = self.config.system_prompt or SYSTEM_PROMPT

        tool_results = ""
        if tool_calls:
            tool_results = "\n".join([
                f"Tool {call.tool_name}: {call.result if call.result else f'Error: {call.error}'}"
                for call in tool_calls
            ])

        full_prompt = f"""
        {system_prompt}

        Task: {task.description}

        Context Information:
        {context}

        Tool Execution Results:
        {tool_results}

        Based on the above information, provide a comprehensive and helpful response.
        """

        response = await observability_manager.trace_llm_call(
            provider="ollama",
            model=self.config.model_name,
            prompt=full_prompt,
            call_fn=lambda: self.llm_service.chat([
                {"role": "user", "content": full_prompt}
            ])
        )

        return response

    def _calculate_confidence(self, tool_calls: List[ToolCall], reasoning_steps: List[str]) -> float:
        """Calculate confidence score based on execution quality."""
        confidence = 0.5  # Base confidence

        # Increase confidence for successful tool calls
        successful_tools = sum(1 for call in tool_calls if call.result and not call.error)
        if tool_calls:
            confidence += (successful_tools / len(tool_calls)) * 0.3

        # Increase confidence for thorough reasoning
        if len(reasoning_steps) > 3:
            confidence += 0.2

        return min(1.0, confidence)

    def _get_role_context(self) -> Optional[str]:
        """Get role-specific context and instructions."""
        role_contexts = {
            AgentRole.DEVOPS: "You are a DevOps specialist. Focus on infrastructure, deployment, monitoring, and operational excellence.",
            AgentRole.SECURITY: "You are a security specialist. Prioritize security best practices, vulnerability assessment, and compliance.",
            AgentRole.MONITORING: "You are a monitoring specialist. Focus on observability, metrics, alerting, and performance analysis.",
            AgentRole.DATABASE: "You are a database specialist. Focus on data management, query optimization, and database administration.",
            AgentRole.INFRASTRUCTURE: "You are an infrastructure specialist. Focus on cloud architecture, networking, and system design.",
        }
        return role_contexts.get(self.config.role)

    # Multi-agent coordination methods
    async def delegate_to_specialist(
        self,
        task: AgentTask,
        specialist_role: AgentRole
    ) -> AgentResponse:
        """Delegate a task to a specialist agent."""
        # Create specialist agent
        specialist_config = AgentConfig(
            role=specialist_role,
            capabilities=[AgentCapability.TOOL_USE, AgentCapability.RAG_RETRIEVAL, AgentCapability.ANALYSIS]
        )

        specialist = DevOpsAgent(specialist_config, self.session)
        await specialist.initialize()

        # Execute with specialist
        return await specialist._execute_task(task)

    async def collaborate_on_task(
        self,
        task: AgentTask,
        collaborators: List[AgentRole]
    ) -> Dict[str, AgentResponse]:
        """Collaborate with other specialist agents on a complex task."""
        results = {}

        # Execute with each collaborator
        for role in collaborators:
            try:
                result = await self.delegate_to_specialist(task, role)
                results[role.value] = result
            except Exception as e:
                logger.error(f"Collaboration with {role.value} failed: {e}")
                results[role.value] = AgentResponse(
                    content=f"Collaboration failed: {str(e)}",
                    confidence_score=0.0
                )

        return results

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

    def _format_messages_for_llm(
        self, memory: ConversationMemory, current_message: str
    ) -> list[dict]:
        """Format conversation history for LLM."""
        messages = []

        # Add system message
        messages.append(
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        )

        # Add previous messages from memory
        for msg in memory.get_last_n_messages(6):  # Keep last 6 messages
            messages.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                }
            )

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
            f"- {tool_name}: {result}" for tool_name, result in tool_results.items()
        )

        return f"""Based on the tool results below, provide a comprehensive answer to the user's question.

User Question: {user_query}

Tool Results:
{results_text}

Please synthesize these results into a clear, actionable response."""

    def _error_response(
        self, error: str, memory: Optional[ConversationMemory] = None
    ) -> dict[str, Any]:
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
