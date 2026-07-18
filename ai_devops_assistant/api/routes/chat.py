"""Chat endpoints for the DevOps assistant, request/response and streaming."""

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ai_devops_assistant.agents.agent import get_agent
from ai_devops_assistant.agents.events import EventType
from ai_devops_assistant.api.auth import limiter
from ai_devops_assistant.api.dependencies import get_db_session
from ai_devops_assistant.api.schemas import ChatRequest, ChatResponse, ToolCall
from ai_devops_assistant.config.settings import settings
from ai_devops_assistant.database.queries import add_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Events forwarded to the browser. The DONE payload keeps tool_results, which can
# be large, so the SSE layer strips them: the UI shows a summary on the chip and
# fetches the full payload on demand.
_HEAVY_DONE_FIELDS = ("tool_results",)


@router.post("", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    """Process chat request and return response.

    Args:
        request: Raw HTTP request (required by the rate limiter)
        chat_request: Chat request with message and optional session ID
        db_session: Database session

    Returns:
        ChatResponse: Chat response with AI response and tool usage info
    """
    try:
        # Get or create session
        session_id = chat_request.session_id or str(uuid.uuid4())

        # Get agent
        agent = await get_agent(db_session)

        # Process message
        logger.info(f"Processing chat request for session: {session_id}")
        result = await agent.chat(
            message=chat_request.message,
            session_id=session_id,
            use_rag=True,
        )

        if not result.get("success"):
            logger.error(f"Agent error: {result.get('message')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to process request"),
            )

        # Format tool calls
        tool_calls = []
        for tool_call in result.get("tool_calls", []):
            tool_calls.append(
                ToolCall(
                    tool_name=tool_call.get("name", "unknown"),
                    parameters=tool_call.get("parameters", {}),
                    result=result.get("tool_results", {}).get(tool_call.get("name")),
                )
            )

        # Store in database
        try:
            # Store user message
            await add_chat_message(
                db_session,
                session_id,
                "user",
                chat_request.message,
            )

            # Store assistant response
            await add_chat_message(
                db_session,
                session_id,
                "assistant",
                result.get("message", ""),
                tools_used=[tc.tool_name for tc in tool_calls],
            )
        except Exception as e:
            logger.warning(f"Failed to store chat in database: {e}")

        return ChatResponse(
            session_id=session_id,
            message=result.get("message", ""),
            tool_calls=tool_calls if tool_calls else None,
            thinking=result.get("thinking"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


@router.get("/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get information about a chat session.

    Args:
        session_id: Session ID
        db_session: Database session

    Returns:
        dict: Session information
    """
    try:
        from ai_devops_assistant.database.queries import get_chat_messages, get_chat_session

        session = await get_chat_session(db_session, session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        messages = await get_chat_messages(db_session, session_id, limit=50)

        return {
            "session_id": session.id,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "message_count": session.message_count,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content[:200],  # Truncate for response
                    "created_at": m.created_at,
                }
                for m in messages
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve session",
        )


@router.post("/stream")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> EventSourceResponse:
    """Stream a chat response as server-sent events.

    POST rather than GET, which means the browser's native EventSource cannot be
    used and the client reads the body with fetch + ReadableStream instead. That
    is deliberate: prompts are long, and a GET would put user messages into every
    access log and proxy trace.

    Args:
        request: Raw HTTP request (rate limiter, and disconnect detection)
        chat_request: Chat request with message and optional session ID
        db_session: Database session

    Returns:
        EventSourceResponse streaming status/plan/tool/token events, then done.
    """
    session_id = chat_request.session_id or str(uuid.uuid4())
    agent = await get_agent(db_session)

    # Persisted before streaming starts. If the client disconnects mid-stream the
    # user's message is still part of the conversation.
    try:
        await add_chat_message(db_session, session_id, "user", chat_request.message)
    except Exception as e:  # matches the non-streaming route's behaviour
        logger.warning(f"Failed to store user message: {e}")

    async def event_generator() -> AsyncIterator[dict]:
        assistant_reply = ""
        tools_used: list[str] = []
        try:
            async for event in agent.chat_stream(
                message=chat_request.message,
                session_id=session_id,
                use_rag=True,
            ):
                # Stop promptly when the user hits Stop; without this the agent
                # would keep working and burn tokens for a response nobody reads.
                if await request.is_disconnected():
                    logger.info(f"Client disconnected, ending stream for {session_id}")
                    break

                payload = event.data
                if event.type is EventType.ERROR:
                    # Agent errors carry raw provider detail — upstream API
                    # messages, request ids, billing state. Log it, but send the
                    # browser something that says what happened and nothing about
                    # our infrastructure.
                    logger.error(f"Agent error for session {session_id}: {payload.get('message')}")
                    payload = {
                        "message": "The assistant could not complete this request.",
                        "recoverable": bool(payload.get("recoverable", False)),
                    }
                elif event.type is EventType.DONE:
                    assistant_reply = payload.get("message", "")
                    tools_used = [c["name"] for c in payload.get("tool_calls", [])]
                    payload = {k: v for k, v in payload.items() if k not in _HEAVY_DONE_FIELDS}
                elif event.type is EventType.TOKEN:
                    assistant_reply += payload.get("t", "")
                elif event.type is EventType.TOOL_END:
                    tools_used.append(payload.get("name", "unknown"))

                yield {"event": event.type.value, "data": json.dumps(payload)}

        except Exception as e:
            logger.error(f"Streaming chat failed: {e}", exc_info=True)
            yield {
                "event": EventType.ERROR.value,
                "data": json.dumps({"message": "Internal server error", "recoverable": False}),
            }
        finally:
            # In finally so a stopped or failed generation is still persisted.
            # Without this a stopped response vanishes from history and the
            # sidebar shows a user message with no reply.
            if assistant_reply:
                try:
                    await add_chat_message(
                        db_session,
                        session_id,
                        "assistant",
                        assistant_reply,
                        tools_used=list(dict.fromkeys(tools_used)),
                    )
                except Exception as e:
                    logger.warning(f"Failed to store assistant message: {e}")

    return EventSourceResponse(event_generator())
