"""SQL query tool for safe database queries."""

import logging
import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_devops_assistant.config.constants import ERROR_SQL_INJECTION_DETECTED, MAX_SQL_RESULT_ROWS
from ai_devops_assistant.database.context import get_current_session
from ai_devops_assistant.tools.base import BaseTool
from ai_devops_assistant.tools.sql_correction import _convert_sqlite_syntax, validate_and_fix_sql

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
        self._session: AsyncSession | None = None
        self._schema_cache: dict[str, list[str]] | None = None

    @property
    def session(self) -> AsyncSession | None:
        """The caller's session.

        Prefers the request-scoped context so this shared tool instance never
        serves one request using another's session. self._session remains for
        direct construction in tests and scripts.
        """
        return get_current_session() or self._session

    def set_session(self, session: AsyncSession) -> None:
        """Set database session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session
        # A new session may point at a different database, so the cached schema
        # from the previous one must not be reused.
        self._schema_cache = None

    async def _get_schema(self) -> dict[str, list[str]]:
        """Reflect table -> columns for the current connection, cached.

        Reflection is a per-query round trip otherwise, and the correction engine
        needs the schema on every call.
        """
        if self._schema_cache is not None:
            return self._schema_cache
        if not self.session:
            return {}

        def _reflect(connection: Any) -> dict[str, list[str]]:
            inspector = inspect(connection)
            return {
                table: [col["name"] for col in inspector.get_columns(table)]
                for table in inspector.get_table_names()
            }

        try:
            connection = await self.session.connection()
            self._schema_cache = await connection.run_sync(_reflect)
        except Exception as e:
            # Correction is an enhancement; without a schema the query is simply
            # run as written rather than the whole tool failing.
            logger.warning(f"Could not reflect database schema: {e}")
            self._schema_cache = {}
        return self._schema_cache

    async def _dialect_name(self) -> str:
        """Name of the current connection's dialect ('sqlite', 'postgresql', ...)."""
        if not self.session:
            return ""
        bind = self.session.get_bind()
        return getattr(getattr(bind, "dialect", None), "name", "") or ""

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

        # Block comment sequences and stored-procedure prefixes.
        # The semicolon rule comes from MCP's is_safe_select_query: it stops a
        # second statement being appended after an approved SELECT. A single
        # trailing semicolon is normal and harmless, so only interior ones are
        # rejected. This tool's guard is the union of the two projects' rules.
        dangerous_tokens = ["--", "/*", "*/"]
        for token in dangerous_tokens:
            if token in query_upper:
                return False, f"Query contains dangerous token: {token}"

        if ";" in query_upper.rstrip().rstrip(";"):
            return False, "Query contains a statement separator (;)"

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

    # Narrows BaseTool.execute(**kwargs) to this tool's named parameters. The
    # registry always dispatches by keyword and validate_parameters() guards the
    # required ones, so the narrowing is deliberate; mypy cannot express it.
    async def execute(self, query: str, limit: int | None = None, **kwargs) -> dict[str, Any]:  # type: ignore[override]
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

            effective_query, corrections = await self._correct(query)
            if effective_query is None:
                # Correction failed and explained why (unknown table/column, with
                # suggestions). That message is more useful than the database's.
                return {"success": False, "error": corrections["error"]}

            # Execute query
            result = await self.session.execute(text(effective_query))
            rows = result.fetchall()[:actual_limit]

            # Format results (SQLAlchemy 2.0 rows convert via ._mapping)
            formatted_rows = [dict(row._mapping) for row in rows]

            return {
                "success": True,
                "rows": formatted_rows,
                "count": len(formatted_rows),
                "limited": len(rows) >= actual_limit,
                **corrections,
            }

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "success": False,
                "error": f"SQL execution failed: {str(e)}",
            }

    async def _correct(self, query: str) -> tuple[str | None, dict[str, Any]]:
        """Repair hallucinated table/column names before executing.

        Returns (sql_to_run, extra_result_fields). sql_to_run is None when
        correction failed, in which case extra_result_fields carries the "error"
        explaining why, with suggestions and a schema preview.

        Two hazards are handled here, and both are easy to get wrong:

        1. Dialect. _convert_sqlite_syntax rewrites EXTRACT() into strftime(),
           which is right for sqlite and broken on postgres. Tests run on
           aiosqlite and production runs on postgres, so applying it
           unconditionally would pass every test and fail in production. It is
           gated on the live connection's dialect.

        2. Re-validation. The corrector rewrites the query string *after*
           validate_sql_injection already approved the original, via regex
           substitution of table names. The rewritten string is therefore
           something the guard has never seen, so it is checked again. Never
           execute SQL the guard has not approved in its final form.
        """
        schema = await self._get_schema()
        if not schema:
            return query, {}

        candidate = query
        if await self._dialect_name() == "sqlite":
            candidate = _convert_sqlite_syntax(candidate)

        ok, message, fixed = validate_and_fix_sql(candidate, schema)
        if not ok:
            return None, {"error": message, "original_query": query}

        # Re-validate: `fixed` is a different string from the one approved above.
        is_safe, error = self.validate_sql_injection(fixed)
        if not is_safe:
            logger.error(
                "Correction produced a query that failed the safety guard; refusing to run it. "
                f"original={query!r} corrected={fixed!r} reason={error}"
            )
            return None, {"error": f"Corrected query failed validation: {error}"}

        if fixed.strip() == query.strip():
            return fixed, {}

        logger.info(f"Auto-corrected SQL: {query!r} -> {fixed!r}")
        return fixed, {"corrected": True, "original_query": query, "corrected_query": fixed}

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
