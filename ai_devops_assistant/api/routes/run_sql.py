"""SQL query endpoint for DevOps assistant."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.api.dependencies import get_db_session
from ai_devops_assistant.api.schemas import SQLQueryRequest, SQLQueryResponse
from ai_devops_assistant.tools.sql_tool import SQLQueryTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/run_sql", tags=["sql"])


@router.post("", response_model=SQLQueryResponse)
async def run_sql(
    request: SQLQueryRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> SQLQueryResponse:
    """Execute a safe SQL query and return results.

    Args:
        request: SQL query request
        db_session: Database session

    Returns:
        SQLQueryResponse: Query results
    """
    try:
        # Initialize SQL tool
        sql_tool = SQLQueryTool()
        sql_tool.set_session(db_session)

        # Validate query safety before execution
        is_safe, validation_error = sql_tool.validate_sql_injection(request.query)
        if not is_safe:
            raise HTTPException(
                status_code=400,
                detail=validation_error or "Query is not allowed",
            )

        # Execute query
        logger.info(f"Executing SQL query: {request.query[:100]}...")
        result = await sql_tool.execute(
            query=request.query,
            limit=request.limit,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Query execution failed"),
            )

        return SQLQueryResponse(
            rows=result["rows"],
            count=result["count"],
            execution_time_ms=0.0,  # TODO: Add timing
        )

    except Exception as e:
        logger.error(f"SQL query error: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Query execution failed: {str(e)}",
        )
