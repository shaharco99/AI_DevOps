"""SQL query tool for safe database queries."""

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.config.constants import ERROR_SQL_INJECTION_DETECTED, MAX_SQL_RESULT_ROWS
from ai_devops_assistant.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SQLQueryTool(BaseTool):
    """Tool for executing SQL queries safely."""

    def __init__(self):
        """Initialize SQL tool."""
        super().__init__(
            name="sql_query_tool",
            description="Execute SQL queries to retrieve data from the application database. "
            "Supports SELECT queries only for security.",
        )
        self.session: AsyncSession | None = None

    def set_session(self, session: AsyncSession) -> None:
        """Set database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    def validate_sql_injection(self, query: str) -> tuple[bool, str | None]:
        """Check for potential SQL injection patterns.

        Args:
            query: SQL query to validate

        Returns:
            tuple: (is_safe, error_message)
        """
        query_upper = query.upper().strip()

        # Only allow SELECT statements
        if not query_upper.startswith("SELECT"):
            return False, "Only SELECT queries are allowed"

        # Block dangerous keywords as whole words only — substring matching
        # falsely flags identifiers like created_at (CREATE) or updated_at (UPDATE)
        dangerous_keywords = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "ALTER",
            "CREATE",
            "TRUNCATE",
            "EXEC",
            "EXECUTE",
        ]

        for keyword in dangerous_keywords:
            if re.search(rf"\b{keyword}\b", query_upper):
                return False, f"Query contains dangerous keyword: {keyword}"

        # Block comment sequences and stored-procedure prefixes
        dangerous_tokens = ["--", "/*", "*/"]
        for token in dangerous_tokens:
            if token in query_upper:
                return False, f"Query contains dangerous token: {token}"

        if re.search(r"\b(XP|SP)_", query_upper):
            return False, "Query contains dangerous stored-procedure prefix"

        # Check for common injection patterns
        injection_patterns = [
            r"'[\s]*OR[\s]*'1'[\s]*=[\s]*'1",  # Classic or 1=1
            r"'[\s]*OR[\s]*1[\s]*=[\s]*1",
            r"UNION[\s]+SELECT",  # Union-based injection
            r";\s*DROP",
            r";\s*DELETE",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, query_upper):
                return False, ERROR_SQL_INJECTION_DETECTED

        return True, None

    def validate_parameters(self, **kwargs) -> tuple[bool, str | None]:
        """Validate tool parameters.

        Args:
            **kwargs: Parameters

        Returns:
            tuple: (is_valid, error_message)
        """
        if "query" not in kwargs:
            return False, "Missing 'query' parameter"

        query = kwargs["query"]
        if not isinstance(query, str):
            return False, "Query must be a string"

        # Validate SQL safety
        return self.validate_sql_injection(query)

    async def execute(self, query: str, limit: int | None = None, **kwargs) -> dict[str, Any]:
        """Execute SQL query.

        Args:
            query: SQL query to execute
            limit: Optional row limit
            **kwargs: Additional parameters

        Returns:
            dict: Query results
        """
        if not self.session:
            return {
                "success": False,
                "error": "Database session not configured",
            }

        try:
            # Apply limit
            actual_limit = min(limit or MAX_SQL_RESULT_ROWS, MAX_SQL_RESULT_ROWS)

            # Execute query
            result = await self.session.execute(text(query))
            rows = result.fetchall()[:actual_limit]

            # Format results (SQLAlchemy 2.0 rows convert via ._mapping)
            formatted_rows = [dict(row._mapping) for row in rows]

            return {
                "success": True,
                "rows": formatted_rows,
                "count": len(formatted_rows),
                "limited": len(rows) >= actual_limit,
            }

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "success": False,
                "error": f"SQL execution failed: {str(e)}",
            }

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
                        "description": "SELECT SQL query (injection-safe)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Maximum rows to return (max: {MAX_SQL_RESULT_ROWS})",
                    },
                },
                "required": ["query"],
            },
        }
