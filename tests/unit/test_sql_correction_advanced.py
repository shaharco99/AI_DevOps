"""Advanced SQL correction cases.

Covers the ground MCP's edge-case and join suites held: table inference, complex
joins, case handling and malformed input. Kept separate from
test_sql_correction.py so the basic contract stays readable.
"""

import pytest

from ai_devops_assistant.tools.sql_correction import extract_query_identifiers, validate_and_fix_sql

SCHEMA = {
    "clients": ["client_id", "name", "country", "email"],
    "orders": ["order_id", "client_id", "status", "order_date", "total"],
    "products": ["product_id", "order_id", "product_name", "price"],
}


class TestTableInference:
    """Repairing a query that names columns but forgets the table."""

    def test_infers_the_table_for_an_unambiguous_column(self):
        ok, _, fixed = validate_and_fix_sql("SELECT name", SCHEMA)
        assert ok is True
        assert "FROM clients" in fixed

    def test_infers_a_join_for_a_column_shared_by_two_tables(self):
        """client_id exists in clients and orders, so both are brought in."""
        ok, _, fixed = validate_and_fix_sql("SELECT client_id", SCHEMA)
        assert ok is True
        assert "FROM clients" in fixed
        assert "JOIN orders" in fixed
        assert "ON" in fixed

    def test_inference_leaves_a_complete_query_alone(self):
        ok, _, fixed = validate_and_fix_sql("SELECT name FROM clients", SCHEMA)
        assert ok is True
        assert fixed.strip() == "SELECT name FROM clients"

    def test_columns_are_extracted_without_a_from_clause(self):
        """The precondition for inference; without it inference never runs."""
        _, columns = extract_query_identifiers("SELECT name")
        assert "name" in columns


class TestJoins:
    def test_two_table_join_with_aliases(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT c.name, o.total FROM clients c JOIN orders o ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is True

    def test_three_table_join(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT c.name, o.total, p.price FROM clients c "
            "JOIN orders o ON c.client_id = o.client_id "
            "JOIN products p ON p.order_id = o.order_id",
            SCHEMA,
        )
        assert ok is True

    def test_left_join(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT c.name FROM clients c LEFT JOIN orders o ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is True

    def test_join_with_aggregation(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT c.name, SUM(o.total) FROM clients c "
            "JOIN orders o ON c.client_id = o.client_id GROUP BY c.name",
            SCHEMA,
        )
        assert ok is True

    def test_join_with_a_bad_column_is_rejected(self):
        ok, message, _ = validate_and_fix_sql(
            "SELECT c.nonexistent FROM clients c JOIN orders o ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is False
        assert "nonexistent" in message

    def test_misspelled_table_in_a_join_is_corrected(self):
        ok, _, fixed = validate_and_fix_sql(
            "SELECT c.name FROM clientss c JOIN orders o ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is True
        assert "clientss" not in fixed


class TestWildcards:
    def test_select_star(self):
        ok, _, _ = validate_and_fix_sql("SELECT * FROM clients", SCHEMA)
        assert ok is True

    def test_prefixed_star(self):
        """`c.*` must not be treated as a column named '*'."""
        ok, _, _ = validate_and_fix_sql("SELECT c.* FROM clients c", SCHEMA)
        assert ok is True

    def test_star_alongside_named_columns(self):
        ok, _, _ = validate_and_fix_sql("SELECT *, name FROM clients", SCHEMA)
        assert ok is True


class TestCaseHandling:
    def test_uppercase_table_name_is_normalised(self):
        ok, _, fixed = validate_and_fix_sql("SELECT name FROM CLIENTS", SCHEMA)
        assert ok is True
        assert "clients" in fixed

    def test_lowercase_keywords_are_accepted(self):
        ok, _, _ = validate_and_fix_sql("select name from clients", SCHEMA)
        assert ok is True

    def test_mixed_case_keywords_are_accepted(self):
        ok, _, _ = validate_and_fix_sql("SeLeCt name FrOm clients", SCHEMA)
        assert ok is True


class TestMalformedInput:
    @pytest.mark.parametrize("query", ["", "   ", "SELECT", "SELECT FROM"])
    def test_degenerate_queries_are_rejected_not_crashed(self, query):
        ok, message, _ = validate_and_fix_sql(query, SCHEMA)
        assert ok is False
        assert message, "a rejection must explain itself"

    def test_gibberish_is_rejected(self):
        ok, _, _ = validate_and_fix_sql("SELCT nonsense FRM nowhere", SCHEMA)
        assert ok is False

    def test_a_very_long_query_terminates(self):
        """The correction loop is bounded; a pathological input must not hang."""
        query = "SELECT " + ", ".join(["name"] * 200) + " FROM clients"
        ok, _, _ = validate_and_fix_sql(query, SCHEMA)
        assert ok is True

    def test_unicode_in_a_literal_is_tolerated(self):
        ok, _, _ = validate_and_fix_sql("SELECT name FROM clients WHERE country = 'Việt'", SCHEMA)
        assert ok is True


class TestWhitespaceAndFormatting:
    def test_multiline_query(self):
        ok, _, _ = validate_and_fix_sql(
            "SELECT\n  c.name,\n  o.total\nFROM clients c\nJOIN orders o\n  ON c.client_id = o.client_id",
            SCHEMA,
        )
        assert ok is True

    def test_tabs_and_extra_spaces(self):
        ok, _, _ = validate_and_fix_sql("SELECT\t\tname   FROM\t clients", SCHEMA)
        assert ok is True


class TestClauses:
    @pytest.mark.parametrize(
        "suffix",
        [
            "WHERE country = 'USA'",
            "ORDER BY name",
            "GROUP BY country",
            "LIMIT 10",
            "WHERE country = 'USA' ORDER BY name LIMIT 5",
        ],
    )
    def test_trailing_clauses_are_preserved(self, suffix):
        query = f"SELECT name, country FROM clients {suffix}"
        ok, _, fixed = validate_and_fix_sql(query, SCHEMA)
        assert ok is True
        assert suffix.split()[0] in fixed

    def test_a_bad_column_in_a_where_clause_is_caught(self):
        ok, message, _ = validate_and_fix_sql("SELECT name FROM clients WHERE c.bogus = 1", SCHEMA)
        assert ok is False
        assert "bogus" in message
