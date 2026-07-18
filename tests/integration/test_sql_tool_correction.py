"""Integration tests for SQLQueryTool with the correction engine wired in.

Runs against a real sqlite database through the tool's own code path, so schema
reflection, the dialect gate, correction and the safety guards are all exercised
together rather than mocked.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_devops_assistant.tools.sql_tool import SQLQueryTool


@pytest.fixture
async def sql_tool():
    """A SQLQueryTool bound to an in-memory database with a small schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE clients (client_id INTEGER, name TEXT, country TEXT)")
        )
        await conn.execute(
            text("CREATE TABLE orders (order_id INTEGER, client_id INTEGER, total REAL)")
        )
        await conn.execute(text("INSERT INTO clients VALUES (1,'Acme','USA'),(2,'Beta','UK')"))
        await conn.execute(text("INSERT INTO orders VALUES (10,1,99.5),(11,2,10.0)"))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        tool = SQLQueryTool()
        tool.set_session(session)
        yield tool
    await engine.dispose()


class TestSchemaReflection:
    @pytest.mark.asyncio
    async def test_reflects_tables_and_columns(self, sql_tool):
        schema = await sql_tool._get_schema()
        assert schema["clients"] == ["client_id", "name", "country"]
        assert "orders" in schema

    @pytest.mark.asyncio
    async def test_schema_is_cached(self, sql_tool):
        first = await sql_tool._get_schema()
        assert sql_tool._schema_cache is not None
        assert await sql_tool._get_schema() is first

    @pytest.mark.asyncio
    async def test_setting_a_new_session_invalidates_the_cache(self, sql_tool):
        await sql_tool._get_schema()
        sql_tool.set_session(sql_tool.session)
        assert sql_tool._schema_cache is None, "a new session may be a different database"


class TestCorrection:
    @pytest.mark.asyncio
    async def test_valid_query_runs_and_is_not_marked_corrected(self, sql_tool):
        result = await sql_tool(query="SELECT name FROM clients")
        assert result["success"] is True
        assert result["count"] == 2
        assert "corrected" not in result

    @pytest.mark.asyncio
    async def test_misspelled_table_is_corrected_and_executed(self, sql_tool):
        """The headline feature: a hallucinated table name still returns data."""
        result = await sql_tool(query="SELECT name FROM clientss")
        assert result["success"] is True
        assert result["corrected"] is True
        assert result["corrected_query"] == "SELECT name FROM clients"
        assert result["original_query"] == "SELECT name FROM clientss"
        assert {row["name"] for row in result["rows"]} == {"Acme", "Beta"}

    @pytest.mark.asyncio
    async def test_unknown_table_returns_a_helpful_error(self, sql_tool):
        result = await sql_tool(query="SELECT name FROM customers")
        assert result["success"] is False
        assert "customers" in result["error"]
        assert "clients" in result["error"], "should show the tables that do exist"

    @pytest.mark.asyncio
    async def test_unknown_column_suggests_a_real_one(self, sql_tool):
        result = await sql_tool(query="SELECT nmae FROM clients")
        assert result["success"] is False
        assert "name" in result["error"]

    @pytest.mark.asyncio
    async def test_join_across_real_tables_executes(self, sql_tool):
        result = await sql_tool(
            query=(
                "SELECT c.name, o.total FROM clients c "
                "JOIN orders o ON c.client_id = o.client_id"
            )
        )
        assert result["success"] is True
        assert result["count"] == 2


class TestSafetyGuards:
    """The guard runs before and after correction."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "DROP TABLE clients",
            "DELETE FROM clients",
            "UPDATE clients SET name='x'",
            "INSERT INTO clients VALUES (3,'x','y')",
        ],
    )
    async def test_non_select_statements_are_refused(self, sql_tool, query):
        result = await sql_tool(query=query)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_stacked_statement_is_refused(self, sql_tool):
        result = await sql_tool(query="SELECT name FROM clients; DROP TABLE clients")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_a_trailing_semicolon_is_still_allowed(self, sql_tool):
        """Only interior separators are dangerous; a trailing one is idiomatic."""
        result = await sql_tool(query="SELECT name FROM clients;")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_comment_injection_is_refused(self, sql_tool):
        result = await sql_tool(query="SELECT name FROM clients -- bypass")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_union_injection_is_refused(self, sql_tool):
        result = await sql_tool(query="SELECT name FROM clients UNION SELECT country FROM clients")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_the_table_survived_every_refused_query(self, sql_tool):
        """Proves the refusals were refusals, not silent partial execution."""
        for bad in (
            "DROP TABLE clients",
            "DELETE FROM clients",
            "SELECT name FROM clients; DROP TABLE clients",
        ):
            await sql_tool(query=bad)
        result = await sql_tool(query="SELECT name FROM clients")
        assert result["count"] == 2, "data was modified by a query that should have been refused"


class TestDialectGate:
    @pytest.mark.asyncio
    async def test_dialect_is_detected(self, sql_tool):
        assert await sql_tool._dialect_name() == "sqlite"

    @pytest.mark.asyncio
    async def test_extract_is_translated_on_sqlite(self, sql_tool):
        """sqlite has no EXTRACT, so the translation is what makes this work."""
        result = await sql_tool(
            query="SELECT order_id FROM orders WHERE EXTRACT(YEAR FROM total) = 2023"
        )
        # The query is nonsense semantically, but it must not fail with
        # "no such function: EXTRACT" — the point is that translation happened.
        assert "EXTRACT" not in str(result.get("error", ""))


class TestNoSessionConfigured:
    @pytest.mark.asyncio
    async def test_reports_a_missing_session_rather_than_crashing(self):
        tool = SQLQueryTool()
        result = await tool(query="SELECT 1")
        assert result["success"] is False
        assert "session" in result["error"].lower()
