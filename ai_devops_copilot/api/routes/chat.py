"""Chat endpoint for DevOps assistant."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_copilot.agents.agent import get_agent
from ai_devops_copilot.api.dependencies import get_db_session
from ai_devops_copilot.api.schemas import ChatRequest, ChatResponse, ToolCall
from ai_devops_copilot.database.queries import add_chat_message, create_chat_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    """Process chat request and return response.
    
    Args:
        request: Chat request with message and optional session ID
        db_session: Database session
        
    Returns:
        ChatResponse: Chat response with AI response and tool usage info
    """
    try:
        # Get or create session
        session_id = request.session_id or str(uuid.uuid4())
        
        # Get agent
        agent = await get_agent(db_session)

        # Process message
        logger.info(f"Processing chat request for session: {session_id}")
        result = await agent.chat(
            message=request.message,
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
                request.message,
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
        from ai_devops_copilot.database.queries import get_chat_session, get_chat_messages

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
