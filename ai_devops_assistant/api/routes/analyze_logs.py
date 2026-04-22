"""Log analysis endpoint for DevOps assistant."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.api.dependencies import get_db_session
from ai_devops_assistant.api.schemas import LogAnalysisRequest, LogEntry
from ai_devops_assistant.tools.log_tool import LogAnalysisTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze_logs", tags=["logs"])


@router.post("", response_model=list[LogEntry])
async def analyze_logs(
    request: LogAnalysisRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> list[LogEntry]:
    """Analyze and search logs.
    
    Args:
        request: Log analysis request
        db_session: Database session
        
    Returns:
        list[LogEntry]: Matching log entries
    """
    try:
        # Initialize log tool
        log_tool = LogAnalysisTool()
        log_tool.set_session(db_session)
        
        # Search logs
        logger.info(f"Searching logs with query: {request.query}")
        result = await log_tool.execute(
            query=request.query,
            log_type="application",
            time_range_hours=request.time_range_hours,
            limit=request.limit,
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Log search failed"),
            )
        
        logs = result["logs"]
        
        # Convert to response format
        log_entries = []
        for log in logs:
            log_entries.append(LogEntry(
                timestamp=log["timestamp"],
                level=log["level"],
                message=log["message"],
                source=log.get("source", "unknown"),
            ))
        
        return log_entries
        
    except Exception as e:
        logger.error(f"Log analysis error: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Log analysis failed: {str(e)}",
        )