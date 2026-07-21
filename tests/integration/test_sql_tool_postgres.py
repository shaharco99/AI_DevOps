"""SQLQueryTool against a real PostgreSQL database.

The rest of the suite runs on aiosqlite, and that is exactly the problem these
tests exist for: the correction engine carries sqlite-specific SQL translation,
so a bug there passes every sqlite test and only surfaces in production.

Skipped unless a Postgres is reachable. To run them:

    docker run -d --name pg-test -e POSTGRES_PASSWORD=testpw \\
        -e POSTGRES_DB=testdb -p 55432:5432 postgres:15-alpine
    TEST_POSTGRES_URL=postgresql+asyncpg://postgres:testpw@127.0.0.1:55432/testdb \\
        pytest tests/integration/test_sql_tool_postgres.py

CI should set TEST_POSTGRES_URL against its postgres service so these are not
silently skipped there.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_devops_assistant.tools.sql_correction import _convert_sqlite_syntax
from ai_devops_assistant.tools.sql_tool import SQLQueryTool

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="TEST_POSTGRES_URL not set; see this module's docstring to run these",
    ),
]


@pytest.fixture
async def pg_tool():
    """A SQLQueryTool bound to a real Postgres database."""
    engine = create_async_engine(POSTGRES_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS pg_orders"))
        await conn.execute(
            text("CREATE TABLE pg_orders (order_id INT, total NUMERIC, order_date DATE)")
        )
        await conn.execute(
            text("INSERT INTO pg_orders VALUES (1, 10, '2023-06-15'), (2, 20, '2024-02-01')")
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        tool = SQLQueryTool()
        tool.set_session(session)
        yield tool

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS pg_orders"))
    await engine.dispose()


class TestDialectGate:
    """The landmine: sqlite translation must never be applied to Postgres."""

    @pytest.mark.asyncio
    async def test_dialect_is_detected_as_postgresql(self, pg_tool):
        assert await pg_tool._dialect_name() == "postgresql"

    @pytest.mark.asyncio
    async def test_extract_runs_natively_and_is_not_rewritten(self, pg_tool):
        """EXTRACT is native Postgres. Rewriting it to strftime() breaks the query.

        Every sqlite-backed test passes whether or not the gate exists, so this
        is the test that actually holds the gate in place.
        """
        result = await pg_tool(
            query="SELECT order_id FROM pg_orders WHERE EXTRACT(YEAR FROM order_date) = 2023"
        )
        assert result["success"] is True, result.get("error")
        assert result["count"] == 1
        assert result["rows"][0]["order_id"] == 1
        assert result.get("corrected", False) is False, "query should not have been rewritten"

    @pytest.mark.asyncio
    async def test_the_translation_would_have_broken_this_query(self, pg_tool):
        """Proves the gate guards something real rather than being decoration."""
        query = "SELECT order_id FROM pg_orders WHERE EXTRACT(YEAR FROM order_date) = 2023"
        translated = _convert_sqlite_syntax(query)
        assert "strftime" in translated

        with pytest.raises(Exception) as exc:
            await pg_tool.session.execute(text(translated))
        assert "strftime" in str(exc.value).lower()
        await pg_tool.session.rollback()


class TestCorrectionOnPostgres:
    """The engine itself must work identically on both dialects."""

    @pytest.mark.asyncio
    async def test_schema_reflection_works(self, pg_tool):
        schema = await pg_tool._get_schema()
        assert "pg_orders" in schema
        assert set(schema["pg_orders"]) == {"order_id", "total", "order_date"}

    @pytest.mark.asyncio
    async def test_valid_query_executes(self, pg_tool):
        result = await pg_tool(query="SELECT order_id FROM pg_orders")
        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_misspelled_table_is_corrected(self, pg_tool):
        result = await pg_tool(query="SELECT order_id FROM pg_orderss")
        assert result["success"] is True
        assert result["corrected"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_unknown_column_is_reported(self, pg_tool):
        result = await pg_tool(query="SELECT nonexistent FROM pg_orders")
        assert result["success"] is False
        assert "nonexistent" in result["error"]


class TestSafetyOnPostgres:
    @pytest.mark.asyncio
    async def test_destructive_statements_are_refused(self, pg_tool):
        for query in ("DROP TABLE pg_orders", "DELETE FROM pg_orders"):
            result = await pg_tool(query=query)
            assert result["success"] is False

        surviving = await pg_tool(query="SELECT order_id FROM pg_orders")
        assert surviving["count"] == 2, "a refused statement modified the database"
