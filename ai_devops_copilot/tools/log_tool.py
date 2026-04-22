"""Log analysis tool."""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_copilot.database.models import ApplicationLog
from ai_devops_copilot.tools.base import BaseTool

logger = logging.getLogger(__name__)


class LogAnalysisTool(BaseTool):
    """Tool for analyzing application and pipeline logs."""

    def __init__(self):
        """Initialize log analysis tool."""
        super().__init__(
            name="log_analysis_tool",
            description="Search and analyze application logs and pipeline logs.",
        )
        self.session: Optional[AsyncSession] = None

    def set_session(self, session: AsyncSession) -> None:
        """Set database session."""
        self.session = session

    async def execute(
        self,
        query: str,
        log_type: str = "application",
        level: Optional[str] = None,
        time_range_hours: int = 24,
        limit: int = 100,
        **kwargs,
    ) -> dict[str, Any]:
        """Execute log search.
        
        Args:
            query: Search query
            log_type: Type of logs to search
            level: Optional log level filter
            time_range_hours: Time range in hours
            limit: Maximum logs to return
            **kwargs: Additional parameters
            
        Returns:
            dict: Search results
        """
        if not self.session:
            return {
                "success": False,
                "error": "Database session not configured",
            }

        try:
            if log_type == "application":
                return await self._search_application_logs(
                    query, level, time_range_hours, limit
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown log type: {log_type}",
                }

        except Exception as e:
            logger.error(f"Log search error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _search_application_logs(
        self,
        query: str,
        level: Optional[str] = None,
        time_range_hours: int = 24,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search application logs."""
        try:
            # Build query
            where_clauses = [
                ApplicationLog.created_at >= datetime.utcnow() - timedelta(hours=time_range_hours),
                ApplicationLog.message.ilike(f"%{query}%"),
            ]

            if level:
                where_clauses.append(ApplicationLog.level == level)

            stmt = select(ApplicationLog).where(and_(*where_clauses)).limit(limit)
            result = await self.session.execute(stmt)
            logs = result.scalars().all()

            # Format results
            formatted_logs = [
                {
                    "timestamp": log.created_at,
                    "level": log.level,
                    "message": log.message,
                    "source": log.source,
                }
                for log in logs
            ]

            # Analyze error patterns
            error_count = sum(1 for log in logs if log.level in ["ERROR", "CRITICAL"])
            warning_count = sum(1 for log in logs if log.level == "WARNING")

            return {
                "success": True,
                "logs": formatted_logs,
                "count": len(formatted_logs),
                "error_count": error_count,
                "warning_count": warning_count,
                "analysis": self._analyze_logs(formatted_logs),
            }

        except Exception as e:
            logger.error(f"Application log search error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _analyze_logs(self, logs: list[dict]) -> str:
        """Analyze logs and generate summary."""
        if not logs:
            return "No logs found matching the query."

        # Count by level
        level_counts = {}
        for log in logs:
            level = log.get("level", "UNKNOWN")
            level_counts[level] = level_counts.get(level, 0) + 1

        # Generate summary
        summary_parts = [f"Found {len(logs)} log entries:"]
        for level, count in sorted(level_counts.items()):
            summary_parts.append(f"  - {level}: {count}")

        # Identify error trends
        errors = [log for log in logs if log.get("level") in ["ERROR", "CRITICAL"]]
        if errors:
            summary_parts.append("\nRecent errors:")
            for error in errors[:3]:
                summary_parts.append(f"  - {error.get('message', 'No message')[:100]}")

        return "\n".join(summary_parts)

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    },
                    "log_type": {
                        "type": "string",
                        "enum": ["application", "pipeline"],
                        "description": "Type of logs to search",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        "description": "Optional log level filter",
                    },
                    "time_range_hours": {
                        "type": "integer",
                        "description": "Time range in hours (default: 24)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum logs to return (default: 100)",
                    },
                },
                "required": ["query"],
            },
        }
