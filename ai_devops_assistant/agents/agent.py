"""Advanced AI Agent Framework for DevOps operations."""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_devops_assistant.rag.pipeline import RAGPipeline

from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.agents.events import AgentEvent, EventType, error_event, status_event
from ai_devops_assistant.agents.memory import ConversationMemory, get_session_manager
from ai_devops_assistant.agents.prompts import SYSTEM_PROMPT
from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.observability.ai_observability import observability_manager, trace_context
from ai_devops_assistant.services.llm_service import get_llm_service
from ai_devops_assistant.tools.tool_executor import get_tool_executor

logger = logging.getLogger(__name__)

# How much of a tool result to put in a tool_end event. The full payload stays
# available in the DONE event's tool_results; this is only what the UI shows on a
# chip before the user expands it.
TOOL_SUMMARY_MAX_CHARS = 200


def _messages_to_trace(messages: list[dict[str, str]]) -> str:
    """Flatten messages for the observability trace only, never for a request."""
    return "\n".join(f"{m.get('role', '?')}: {m.get('content', '')}" for m in messages)


def _summarise_tool_result(result: Any) -> str:
    """Render a short, safe summary of a tool result for a tool_end event."""
    if result is None:
        return ""
    if isinstance(result, dict):
        rows = result.get("rows")
        if isinstance(rows, list):
            return f"{len(rows)} row{'s' if len(rows) != 1 else ''}"
    text = str(result)
    if len(text) > TOOL_SUMMARY_MAX_CHARS:
        return text[:TOOL_SUMMARY_MAX_CHARS] + "…"
    return text


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
    capabilities: list[AgentCapability] = field(
        default_factory=lambda: [
            AgentCapability.TOOL_USE,
            AgentCapability.RAG_RETRIEVAL,
            AgentCapability.PLANNING,
        ]
    )
    model_name: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: str | None = None
    tool_allowlist: list[str] | None = None
    max_tool_iterations: int = 5
    enable_planning: bool = True
    enable_reflection: bool = True


@dataclass
class AgentTask:
    """Represents a task for an agent to execute."""

    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 1
    requires_tools: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any | None = None
    error: str | None = None


@dataclass
class AgentResponse:
    """Response from an agent execution."""

    content: str
    # ToolCall objects, not dicts: _execute_task passes the ToolCall instances it
    # built, and chat() reads .tool_name/.parameters/.result off them. Forward
    # reference because ToolCall is defined below.
    tool_calls: list["ToolCall"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    reasoning_steps: list[str] = field(default_factory=list)


class ToolCall:
    """Represents a tool call made by an agent."""

    def __init__(self, tool_name: str, parameters: dict[str, Any]):
        self.tool_name = tool_name
        self.parameters = parameters
        self.result: Any | None = None
        self.error: str | None = None
        self.execution_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
        }


class DevOpsAgent:
    """Advanced AI DevOps Agent with tool use and multi-agent capabilities."""

    def __init__(self, config: AgentConfig | None = None, session: AsyncSession | None = None):
        """Initialize agent.

        Args:
            config: Agent configuration
            session: SQLAlchemy async session for database tools
        """
        self.config = config or AgentConfig()
        # Both are populated by initialize(), not here, so they must be declared
        # Optional — otherwise their inferred type is None and every later use is
        # an error. RAGPipeline is imported lazily inside initialize() to keep the
        # heavy rag/ import off the module import path, hence the string annotation.
        self.llm_service: Any | None = None
        self.tool_executor = get_tool_executor(session)
        self.rag_pipeline: "RAGPipeline | None" = None
        self.session_manager = get_session_manager()
        self.session = session
        self.conversation_memory: ConversationMemory | None = None

        # Agent state
        self.current_task: AgentTask | None = None
        self.execution_history: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        """Initialize agent components."""
        try:
            self.llm_service = await get_llm_service()
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
        self, message: str, session_id: str | None = None, use_rag: bool = True, **kwargs
    ) -> dict[str, Any]:
        """Process user message and generate response with advanced agent capabilities.

        Args:
            message: User input message
            session_id: Conversation session ID
            use_rag: Whether to use RAG for context
            **kwargs: Additional parameters

        Returns:
            Response dictionary with content, metadata, and tool calls
        """
        # Drains chat_stream() rather than reimplementing the loop. Forking the two
        # would let them drift; this keeps a single implementation and guarantees
        # the streaming and non-streaming paths cannot disagree.
        terminal: AgentEvent | None = None
        async for event in self.chat_stream(
            message, session_id=session_id, use_rag=use_rag, **kwargs
        ):
            if event.is_terminal:
                terminal = event

        if terminal is not None and terminal.type is EventType.DONE:
            return {"success": True, **terminal.data}

        error_message = (
            terminal.data.get("message", "unknown error") if terminal is not None else "no response"
        )
        return {
            "success": False,
            "content": f"I apologize, but I encountered an error: {error_message}",
            "message": f"I apologize, but I encountered an error: {error_message}",
            "error": error_message,
            "tool_calls": [],
            "tool_results": {},
            "metadata": {},
            "confidence_score": 0.0,
            "reasoning_steps": [],
            "session_id": session_id,
        }

    async def chat_stream(
        self, message: str, session_id: str | None = None, use_rag: bool = True, **kwargs
    ) -> AsyncIterator[AgentEvent]:
        """Process a user message, emitting progress events as the work happens.

        This is the real implementation of the chat loop; chat() consumes it.

        Args:
            message: User input message
            session_id: Conversation session ID
            use_rag: Whether to use RAG for context
            **kwargs: Additional parameters

        Yields:
            AgentEvent instances. Exactly one terminal event (DONE or ERROR) is
            emitted last, and nothing follows it.
        """
        with trace_context("agent_chat", agent_role=self.config.role.value):
            try:
                # Initialize conversation memory if needed
                if session_id and not self.conversation_memory:
                    self.conversation_memory = self.session_manager.get_or_create_session(
                        session_id
                    )

                task = AgentTask(description=message, context={"session_id": session_id})

                response: AgentResponse | None = None
                async for event in self._execute_task_stream(task, use_rag=use_rag):
                    if event.type is EventType.DONE:
                        # Carries the assembled response; held back so memory and
                        # history are updated before the caller sees the terminal event.
                        response = event.data["response"]
                        continue
                    yield event

                if response is None:  # pragma: no cover - defensive
                    raise RuntimeError("agent produced no response")

                if self.conversation_memory:
                    self.conversation_memory.add_message("user", message)
                    self.conversation_memory.add_message("assistant", response.content)

                self.execution_history.append(
                    {
                        "timestamp": asyncio.get_event_loop().time(),
                        "task": task.description,
                        "response": response.content,
                        "tool_calls": len(response.tool_calls),
                        "confidence": response.confidence_score,
                    }
                )

                yield AgentEvent(
                    type=EventType.DONE,
                    data=self._response_payload(response, session_id),
                )

            except Exception as e:
                logger.error(f"Agent chat failed: {e}", exc_info=True)
                yield error_event(str(e))

    def _response_payload(self, response: AgentResponse, session_id: str | None) -> dict[str, Any]:
        """Build the JSON-safe response body shared by chat() and the DONE event.

        Defined once so the streaming and non-streaming paths cannot describe the
        same response differently.
        """
        return {
            "content": response.content,
            "message": response.content,
            "tool_calls": [
                {"name": call.tool_name, "parameters": call.parameters}
                for call in response.tool_calls
            ],
            "tool_results": {call.tool_name: call.result for call in response.tool_calls},
            "thinking": "\n".join(response.reasoning_steps) or None,
            "metadata": response.metadata,
            "confidence_score": response.confidence_score,
            "reasoning_steps": response.reasoning_steps,
            "session_id": session_id,
        }

    async def _execute_task(self, task: AgentTask, use_rag: bool = True) -> AgentResponse:
        """Execute a task and return the finished response.

        Thin consumer of _execute_task_stream so there is one implementation of
        the loop.
        """
        async for event in self._execute_task_stream(task, use_rag=use_rag):
            if event.type is EventType.DONE:
                response: AgentResponse = event.data["response"]
                return response
        raise RuntimeError("agent produced no response")  # pragma: no cover - defensive

    async def _execute_task_stream(
        self, task: AgentTask, use_rag: bool = True
    ) -> AsyncIterator[AgentEvent]:
        """Execute a task, emitting an event at each observable step.

        The terminal DONE event carries the assembled AgentResponse under
        data["response"]; it is the only event whose payload is not JSON-safe, and
        chat_stream() consumes it rather than forwarding it.
        """
        task.status = "running"
        reasoning_steps = []

        try:
            # Step 1: Gather context
            yield status_event("gathering_context")
            context = await self._gather_context(task, use_rag)
            reasoning_steps.append("Gathered relevant context from knowledge base")

            # Step 2: Plan execution (if planning enabled)
            yield status_event("planning")
            if self.config.enable_planning and AgentCapability.PLANNING in self.config.capabilities:
                plan = await self._create_execution_plan(task, context)
                reasoning_steps.append(f"Created execution plan with {len(plan)} steps")
            else:
                plan = [
                    {"action": "direct_response", "reasoning": "Simple query - direct response"}
                ]

            yield AgentEvent(type=EventType.PLAN, data={"steps": plan})

            # Step 3: Execute plan
            tool_calls = []

            for index, step in enumerate(plan):
                if step["action"] == "tool_call":
                    call_id = f"tc_{index}"
                    yield AgentEvent(
                        type=EventType.TOOL_START,
                        data={
                            "id": call_id,
                            "name": step.get("tool_name", "unknown"),
                            "params": step.get("parameters", {}),
                        },
                    )

                    tool_call = await self._execute_tool_call(step)
                    tool_calls.append(tool_call)
                    reasoning_steps.append(f"Executed tool: {tool_call.tool_name}")

                    yield AgentEvent(
                        type=EventType.TOOL_END,
                        data={
                            "id": call_id,
                            "name": tool_call.tool_name,
                            "ok": tool_call.error is None,
                            "error": tool_call.error,
                            "duration_ms": (
                                round(tool_call.execution_time * 1000, 2)
                                if tool_call.execution_time is not None
                                else None
                            ),
                            # A summary, never the raw result: tool output can be
                            # thousands of rows and would swamp the event stream.
                            "summary": _summarise_tool_result(tool_call.result),
                        },
                    )

                    # Incorporate tool result into context
                    context += f"\nTool result ({tool_call.tool_name}): {tool_call.result}"

                elif step["action"] == "reasoning":
                    # Generate reasoning step
                    reasoning = await self._generate_reasoning_step(context, step)
                    reasoning_steps.append(reasoning)
                    context += f"\nReasoning: {reasoning}"

            # Step 4: Generate final response, streaming real token deltas.
            # This replaces the phase-2 placeholder that chunked an already
            # finished string; the event shape is unchanged, so the frontend
            # needed no modification.
            yield status_event("responding")
            chunks: list[str] = []
            async for chunk in self._stream_final_response(task, context, tool_calls):
                chunks.append(chunk)
                yield AgentEvent(type=EventType.TOKEN, data={"t": chunk})
            final_response = "".join(chunks)
            reasoning_steps.append("Generated final response incorporating all context")

            # Calculate confidence
            confidence = self._calculate_confidence(tool_calls, reasoning_steps)

            task.status = "completed"
            task.result = final_response

            yield AgentEvent(
                type=EventType.DONE,
                data={
                    "response": AgentResponse(
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
                },
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
        if (
            use_rag
            and self.rag_pipeline
            and AgentCapability.RAG_RETRIEVAL in self.config.capabilities
        ):
            try:
                from ai_devops_assistant.rag.pipeline import RAGQuery

                # query() takes a RAGQuery for anything beyond the default top_k;
                # it has no top_k keyword of its own.
                rag_result = await self.rag_pipeline.query(
                    RAGQuery(query=task.description, top_k=3)
                )
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

    async def _create_execution_plan(self, task: AgentTask, context: str) -> list[dict[str, Any]]:
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
                provider=settings.LLM_PROVIDER,
                model=getattr(self.llm_service, "model", self.config.model_name),
                prompt=planning_prompt,
                call_fn=lambda: self.llm_service.chat(
                    [{"role": "user", "content": planning_prompt}]
                ),
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

    async def _execute_tool_call(self, step: dict[str, Any]) -> ToolCall:
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

    async def _generate_reasoning_step(self, context: str, step: dict[str, Any]) -> str:
        """Generate a reasoning step."""
        reasoning_prompt = f"""
        Based on the current context, provide reasoning for the next step.

        Context: {context[:1500]}
        Step: {step}

        Provide concise reasoning (1-2 sentences) explaining this step's purpose.
        """

        try:
            response = await observability_manager.trace_llm_call(
                provider=settings.LLM_PROVIDER,
                model=getattr(self.llm_service, "model", self.config.model_name),
                prompt=reasoning_prompt,
                call_fn=lambda: self.llm_service.chat(
                    [{"role": "user", "content": reasoning_prompt}]
                ),
            )
            return response.strip()
        except Exception:
            return f"Reasoning step: {step.get('reasoning', 'Unknown purpose')}"

    async def _generate_final_response(
        self, task: AgentTask, context: str, tool_calls: list[ToolCall]
    ) -> str:
        """Generate the final response incorporating all context and tool results."""
        # Build comprehensive prompt
        system_prompt = self.config.system_prompt or SYSTEM_PROMPT

        tool_results = ""
        if tool_calls:
            tool_results = "\n".join(
                [
                    f"Tool {call.tool_name}: {call.result if call.result else f'Error: {call.error}'}"
                    for call in tool_calls
                ]
            )

        messages = self._build_response_messages(task, context, tool_results, system_prompt)

        response = await observability_manager.trace_llm_call(
            provider=settings.LLM_PROVIDER,
            model=getattr(self.llm_service, "model", self.config.model_name),
            prompt=_messages_to_trace(messages),
            call_fn=lambda: self.llm_service.chat(messages),
        )

        return response

    def _build_response_messages(
        self,
        task: AgentTask,
        context: str,
        tool_results: str,
        system_prompt: str,
    ) -> list[dict[str, str]]:
        """Build the final-response conversation.

        The system prompt is its own message rather than being concatenated into
        the user turn. That distinction is what a provider needs in order to
        treat instructions and data differently, and it is the seam that phase 6
        fences retrieved documents and tool output behind. Flattening it into one
        string — as this did — makes that impossible to express.
        """
        user_parts = [f"Task: {task.description}"]
        if context:
            user_parts.append(f"Context Information:\n{context}")
        if tool_results:
            user_parts.append(f"Tool Execution Results:\n{tool_results}")
        user_parts.append(
            "Based on the above information, provide a comprehensive and helpful response."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    async def _stream_final_response(
        self, task: AgentTask, context: str, tool_calls: list[ToolCall]
    ) -> AsyncIterator[str]:
        """Stream the final response, yielding real token deltas.

        Falls back to a single non-streaming call if streaming fails *before* any
        token arrives — a provider whose streaming endpoint is broken should not
        take down the whole reply. A failure after the first token is not
        retried, because the caller has already rendered part of the answer.
        """
        system_prompt = self.config.system_prompt or SYSTEM_PROMPT

        tool_results = ""
        if tool_calls:
            tool_results = "\n".join(
                [
                    f"Tool {call.tool_name}: {call.result if call.result else f'Error: {call.error}'}"
                    for call in tool_calls
                ]
            )

        messages = self._build_response_messages(task, context, tool_results, system_prompt)

        started = False
        try:
            async for chunk in self.llm_service.stream_chat(messages):
                if chunk:
                    started = True
                    yield chunk
        except Exception as e:
            if started:
                raise
            logger.warning(f"Streaming unavailable, falling back to a single call: {e}")
            yield await self.llm_service.chat(messages)

    def _calculate_confidence(
        self, tool_calls: list[ToolCall], reasoning_steps: list[str]
    ) -> float:
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

    def _get_role_context(self) -> str | None:
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
        self, task: AgentTask, specialist_role: AgentRole
    ) -> AgentResponse:
        """Delegate a task to a specialist agent."""
        # Create specialist agent
        specialist_config = AgentConfig(
            role=specialist_role,
            capabilities=[
                AgentCapability.TOOL_USE,
                AgentCapability.RAG_RETRIEVAL,
                AgentCapability.ANALYSIS,
            ],
        )

        specialist = DevOpsAgent(specialist_config, self.session)
        await specialist.initialize()

        # Execute with specialist
        return await specialist._execute_task(task)

    async def collaborate_on_task(
        self, task: AgentTask, collaborators: list[AgentRole]
    ) -> dict[str, AgentResponse]:
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
                    content=f"Collaboration failed: {str(e)}", confidence_score=0.0
                )

        return results

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
        self, error: str, memory: ConversationMemory | None = None
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
_agent: DevOpsAgent | None = None


async def get_agent(session: AsyncSession | None = None) -> DevOpsAgent:
    """Get or create DevOps agent.

    Args:
        session: Optional database session

    Returns:
        DevOpsAgent: Agent instance
    """
    global _agent
    if _agent is None:
        _agent = DevOpsAgent(session=session)
        await _agent.initialize()
    return _agent
