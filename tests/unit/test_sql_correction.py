"""Unit tests for the SQL correction engine.

Ported from MCP's ~1000-line suite. These exercise pure functions only — no
database, no chdir, no module globals — which is the payoff for making
validate_and_fix_sql take its schema as an argument.

MCP's originals unwrapped @tool-decorated functions via call_tool/_original_func;
that machinery is gone because the functions are plain callables now.
"""

import pytest

from ai_devops_assistant.tools.sql_correction import (
    _convert_sqlite_syntax,
    _format_schema_preview,
    _suggest_column_candidates,
    extract_query_identifiers,
    fuzzy_match,
    is_safe_select_query,
    parse_natural_language_query,
    validate_and_fix_sql,
)

SCHEMA = {
    "clients": ["client_id", "name", "country", "email"],
    "orders": ["order_id", "client_id", "status", "order_date", "total"],
    "products": ["product_id", "product_name", "price"],
}


class TestIsSafeSelectQuery:
    """MCP's second-opinion guard. sql_tool.validate_sql_injection is the gate."""

    def test_allows_a_plain_select(self):
        ok, _ = is_safe_select_query("SELECT * FROM clients")
        assert ok is True

    @pytest.mark.parametrize(
        "query",
        [
            "INSERT INTO clients VALUES (1)",
            "UPDATE clients SET name='x'",
            "DELETE FROM clients",
            "DROP TABLE clients",
            "ALTER TABLE clients ADD COLUMN x TEXT",
            "CREATE TABLE x (a INT)",
            "TRUNCATE clients",
            "ATTACH DATABASE 'x' AS y",
        ],
    )
    def test_blocks_non_select_statements(self, query):
        ok, message = is_safe_select_query(query)
        assert ok is False
        assert message

    def test_blocks_statement_separators(self):
        ok, _ = is_safe_select_query("SELECT 1 FROM clients; DROP TABLE clients")
        assert ok is False

    @pytest.mark.parametrize("comment", ["--", "/*", "*/"])
    def test_blocks_sql_comments(self, comment):
        ok, _ = is_safe_select_query(f"SELECT name FROM clients {comment} x")
        assert ok is False

    def test_is_case_insensitive(self):
        assert is_safe_select_query("select name from clients")[0] is True
        assert is_safe_select_query("DrOp TaBlE clients")[0] is False


class TestExtractQueryIdentifiers:
    def test_extracts_table_and_columns(self):
        tables, columns = extract_query_identifiers("SELECT name, email FROM clients")
        assert tables == ["clients"]
        assert set(columns) >= {"name", "email"}

    def test_extracts_tables_from_joins(self):
        tables, _ = extract_query_identifiers(
            "SELECT c.name FROM clients c JOIN orders o ON c.client_id = o.client_id"
        )
        assert set(tables) == {"clients", "orders"}

    def test_strips_table_prefixes_from_columns(self):
        _, columns = extract_query_identifiers("SELECT c.name FROM clients c")
        assert "name" in columns
        assert "c.name" not in columns

    def test_ignores_sql_function_names(self):
        """COUNT and friends are not columns; treating them as such breaks validation."""
        _, columns = extract_query_identifiers("SELECT COUNT(order_id) FROM orders")
        assert "COUNT" not in columns

    def test_extracts_the_column_inside_a_function(self):
        _, columns = extract_query_identifiers(
            "SELECT EXTRACT(MONTH FROM o.order_date) FROM orders o"
        )
        assert "order_date" in columns

    def test_handles_select_star(self):
        tables, columns = extract_query_identifiers("SELECT * FROM clients")
        assert tables == ["clients"]
        assert "*" not in columns  # wildcard is not a column name

    def test_strips_column_aliases(self):
        _, columns = extract_query_identifiers("SELECT name AS client_name FROM clients")
        assert "name" in columns

    def test_handles_newlines_and_tabs(self):
        tables, columns = extract_query_identifiers("SELECT\n\tname\nFROM\n\tclients")
        assert tables == ["clients"]
        assert "name" in columns


class TestFuzzyMatch:
    def test_exact_match_wins(self):
        assert fuzzy_match("clients", ["clients", "orders"]) == "clients"

    def test_is_case_insensitive(self):
        assert fuzzy_match("CLIENTS", ["clients"]) == "clients"

    @pytest.mark.parametrize(
        "typo,expected",
        [
            ("clientss", "clients"),
            ("cliets", "clients"),
            ("client", "clients"),
            ("ordres", "orders"),
            ("order", "orders"),
            ("prodcts", "products"),
        ],
    )
    def test_repairs_typos_and_plurals(self, typo, expected):
        assert fuzzy_match(typo, ["clients", "orders", "products"]) == expected

    def test_returns_none_for_unrelated_names(self):
        """A semantically different word is not a typo.

        `customers` against a schema of `clients` returns None on purpose: no
        string-distance measure can bridge that, and silently rewriting it would
        query the wrong table. The caller reports it with a schema preview.
        """
        assert fuzzy_match("customers", ["clients", "orders"]) is None
        assert fuzzy_match("invoices", ["clients", "orders"]) is None

    def test_empty_candidates_returns_none(self):
        assert fuzzy_match("clients", []) is None


class TestSuggestColumnCandidates:
    def test_suggests_a_similar_column(self):
        suggestions = _suggest_column_candidates(["nam"], SCHEMA)
        assert "nam" in suggestions
        assert any("name" in candidate for candidate in suggestions["nam"])

    def test_returns_an_entry_even_when_nothing_matches(self):
        suggestions = _suggest_column_candidates(["zzzzz"], SCHEMA)
        assert suggestions["zzzzz"] == [] or isinstance(suggestions["zzzzz"], list)


class TestFormatSchemaPreview:
    def test_lists_tables_and_columns(self):
        preview = _format_schema_preview(SCHEMA)
        assert "clients" in preview
        assert "orders" in preview

    def test_truncates_to_max_tables(self):
        big = {f"t{i}": ["a"] for i in range(20)}
        preview = _format_schema_preview(big, max_tables=3)
        assert "and 17 more tables" in preview


class TestConvertSqliteSyntax:
    """sqlite-only translation. The caller must gate it on the live dialect."""

    def test_converts_extract_year(self):
        out = _convert_sqlite_syntax("SELECT EXTRACT(YEAR FROM order_date) FROM orders")
        assert "strftime('%Y'" in out
        assert "EXTRACT" not in out

    def test_converts_extract_month_and_day(self):
        assert "strftime('%m'" in _convert_sqlite_syntax("EXTRACT(MONTH FROM d)")
        assert "strftime('%d'" in _convert_sqlite_syntax("EXTRACT(DAY FROM d)")

    def test_leaves_queries_without_extract_untouched(self):
        query = "SELECT name FROM clients WHERE country = 'USA'"
        assert _convert_sqlite_syntax(query) == query

    def test_output_is_invalid_on_postgres_by_design(self):
        """Documents why the caller gates this.

        strftime does not exist in postgres, so applying this to a postgres
        connection turns a working query into UndefinedFunctionError. The gate in
        sql_tool._correct is what prevents that; see
        tests/integration/test_sql_tool_postgres.py for the live proof.
        """
        out = _convert_sqlite_syntax("SELECT EXTRACT(YEAR FROM d) FROM t")
        assert "strftime" in out


class TestValidateAndFixSql:
    def test_accepts_a_valid_query_unchanged(self):
        ok, _, fixed = validate_and_fix_sql("SELECT name FROM clients", SCHEMA)
        assert ok is True
        assert "clients" in fixed

    def test_corrects_a_misspelled_table(self):
        ok, _, fixed = validate_and_fix_sql("SELECT name FROM clientss", SCHEMA)
        assert ok is True
        assert "FROM clients" in fixed

    def test_rejects_an_unknown_table_with_a_schema_preview(self):
        ok, message, _ = validate_and_fix_sql("SELECT name FROM customers", SCHEMA)
        assert ok is False
        assert "customers" in message
        assert "clients" in message, "the error should show what tables do exist"

    def test_rejects_an_unknown_column_with_suggestions(self):
        ok, message, _ = validate_and_fix_sql("SELECT nmae FROM clients", SCHEMA)
        assert ok is False
        assert "nmae" in message
        assert "name" in message

    def test_empty_schema_is_reported_not_crashed(self):
        ok, message, _ = validate_and_fix_sql("SELECT 1", {})
        assert ok is False
        assert "empty" in message.lower()

    def test_accepts_select_star(self):
        ok, _, _ = validate_and_fix_sql("SELECT * FROM clients", SCHEMA)
        assert ok is True

    def test_accepts_a_join_across_known_tables(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT c.name, o.total FROM clients c JOIN orders o ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is True

    def test_is_pure_and_does_not_mutate_the_schema(self):
        before = {k: list(v) for k, v in SCHEMA.items()}
        validate_and_fix_sql("SELECT name FROM clientss", SCHEMA)
        assert SCHEMA == before

    def test_terminates_on_an_unfixable_query(self):
        """The loop is bounded; an unresolvable name must not spin 10 times."""
        ok, message, _ = validate_and_fix_sql("SELECT zzz FROM qqq", SCHEMA)
        assert ok is False
        assert message


class TestParseNaturalLanguageQuery:
    """NL->SQL returns (sql, params); user text is never in the SQL string."""

    def test_location_filter_binds_the_value(self):
        result = parse_natural_language_query("show me all clients from usa", "clients", SCHEMA)
        assert result is not None
        sql, params = result
        assert "country IN (" in sql
        assert "usa" not in sql.lower().replace("clients", "")
        assert any(v.lower() == "usa" for v in params.values())

    def test_year_filter_uses_a_dialect_neutral_range(self):
        """Not strftime: that is sqlite-only and would break on postgres."""
        sql, params = parse_natural_language_query("find orders from 2023", "orders", SCHEMA)
        assert "strftime" not in sql
        assert "EXTRACT" not in sql
        assert params["year_start"] == "2023-01-01"
        assert params["year_end"] == "2024-01-01"

    def test_status_filter_binds_the_value(self):
        sql, params = parse_natural_language_query("show pending orders", "orders", SCHEMA)
        assert "status = :status" in sql
        assert params["status"] == "pending"

    def test_contains_filter_binds_the_wildcards_too(self):
        sql, params = parse_natural_language_query("clients with acme", "clients", SCHEMA)
        assert "LIKE :contains" in sql
        assert params["contains"] == "%acme%"
        assert "%" not in sql

    def test_returns_none_when_nothing_is_recognised(self):
        assert parse_natural_language_query("hello there", "clients", SCHEMA) is None

    def test_returns_none_for_an_unknown_table(self):
        assert parse_natural_language_query("clients from usa", "nope", SCHEMA) is None

    @pytest.mark.parametrize(
        "payload",
        [
            "clients with evil OR one equals one",
            "clients from usa and drop table clients",
            "clients with acme UNION SELECT password",
        ],
    )
    def test_user_text_never_reaches_the_sql_string(self, payload):
        """The whole point of the rewrite: values bind, they do not interpolate."""
        result = parse_natural_language_query(payload, "clients", SCHEMA)
        if result is None:
            return  # unrecognised input is also a safe outcome
        sql, params = result
        # Only schema identifiers and bound placeholders may appear.
        for fragment in ("drop", "union", "password", "evil"):
            assert fragment not in sql.lower(), f"{fragment!r} leaked into SQL: {sql}"

    def test_combines_multiple_filters(self):
        sql, params = parse_natural_language_query(
            "show pending orders from 2023", "orders", SCHEMA
        )
        assert "AND" in sql
        assert params["status"] == "pending"
        assert params["year_start"] == "2023-01-01"
