"""Schema-aware SQL validation and auto-correction.

Ported from the MCP project. Repairs the table and column names LLMs hallucinate
by fuzzy-matching them against the real schema, so a query naming `customers`
when the table is `clients` is corrected rather than rejected.

Every function here is pure: synchronous, no I/O, no module state. The schema is
passed in. That is a deliberate change from the original, which read a
module-global sqlite connection — it is what lets this run against Postgres in
production and be tested without a database.

Two responsibilities live with the *caller*, not here:

- Safety. is_safe_select_query is a second opinion, not the gate. The tool
  wrapping this applies tools/sql_tool.py:validate_sql_injection before and
  again after correction, because correction rewrites the query string.
- Dialect. _convert_sqlite_syntax is sqlite-specific and must only be applied
  when the connection actually is sqlite.
"""
from __future__ import annotations

import re
from typing import Any

# Column-name hints used to pick which column a natural-language filter targets.
_LOCATION_KEYWORDS = (
    "country",
    "state",
    "city",
    "region",
    "location",
    "area",
    "province",
    "territory",
)
_DATE_KEYWORDS = ("date", "created", "updated", "timestamp", "time", "year")
_STATUS_KEYWORDS = ("status", "state", "condition")
_TEXT_KEYWORDS = ("name", "description", "email", "title", "subject", "text")

# Words that follow "from"/"in" but are not places.
_NON_LOCATION_WORDS = frozenset(
    {
        "orders",
        "clients",
        "customers",
        "products",
        "items",
        "pending",
        "completed",
        "processing",
        "cancelled",
        "active",
        "inactive",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
    }
)


def _pick_column(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    """First column whose name contains one of the keywords, else None.

    The returned name is interpolated into SQL, so it must originate from the
    caller's schema. Taking it from `columns` is what makes that true.
    """
    for col in columns:
        lowered = col.lower()
        if any(keyword in lowered for keyword in keywords):
            return col
    return None


def parse_natural_language_query(
    query: str, table_name: str, schema: dict[str, list[str]]
) -> tuple[str, dict[str, Any]] | None:
    """
    Turn a natural-language data question into parameterized SQL.

    A deterministic, LLM-free fast path for the handful of shapes that come up
    constantly ("clients from usa", "orders from 2023", "pending orders"). It is
    a heuristic, not a parser: it returns None whenever it does not recognise
    something, and the caller falls back to the model.

    Returns (sql, params) rather than a SQL string. The original interpolated the
    user's own words straight into the query text; every value is now a bound
    parameter. Column and table names cannot be bound, so they are taken only
    from the caller-supplied schema and re-checked against it before use.

    Handles:
    - Location filters: "from usa", "in canada", "located in uk"
    - Date filters: "from 2023", "in 2023", "since 2023"
    - Status filters: "pending orders", "completed orders"
    - Contains filters: "with acme"

    Args:
        query: The user's question.
        table_name: Table to query; must exist in schema.
        schema: Mapping of table name to its column names.

    Returns:
        (sql, params) or None if nothing was recognised.
    """
    columns = schema.get(table_name, [])
    if not columns:
        return None

    # Identifiers are interpolated (SQL cannot bind them), so they must come from
    # the schema and nowhere else. _pick_column enforces that; this guards the
    # table name the caller passed in.
    if table_name not in schema:
        return None

    query_lower = query.lower()
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    # ---------------------------------------------------------------- location
    location_pattern = (
        r"\b(?:from|in|located in|base in)\s+([a-zA-Z\s]+?)"
        r"(?:\s+(?:with|where|and|order|limit)|$)"
    )
    location_match = re.search(location_pattern, query_lower, re.IGNORECASE)

    if location_match:
        location_value = location_match.group(1).strip()
        if location_value not in _NON_LOCATION_WORDS:
            col = _pick_column(columns, _LOCATION_KEYWORDS)
            if col:
                location_value = re.sub(
                    r"\s+(with|where|and|order|limit|by|in).*$",
                    "",
                    location_value,
                    flags=re.IGNORECASE,
                ).strip()

                # Match a few plausible casings, since the stored form is unknown
                # ('USA' vs 'usa' vs 'New York'). Each is a bound parameter.
                variants = {
                    location_value.upper(),
                    location_value.lower(),
                    " ".join(word.capitalize() for word in location_value.split()),
                }
                placeholders = []
                for i, variant in enumerate(sorted(variants)):
                    key = f"loc_{i}"
                    params[key] = variant
                    placeholders.append(f":{key}")
                where_clauses.append(f"{col} IN ({', '.join(placeholders)})")

    # -------------------------------------------------------------------- year
    year_match = re.search(r"\b(?:from|in|since)\s+(\d{4})\b", query_lower)
    if year_match:
        col = _pick_column(columns, _DATE_KEYWORDS)
        if col:
            year = int(year_match.group(1))
            # A half-open range rather than strftime('%Y', col), which only
            # exists in sqlite. This form works on sqlite and postgres alike and
            # can use an index on the column, which the function call cannot.
            params["year_start"] = f"{year}-01-01"
            params["year_end"] = f"{year + 1}-01-01"
            where_clauses.append(f"{col} >= :year_start AND {col} < :year_end")

    # ------------------------------------------------------------------ status
    status_match = re.search(
        r"\b(pending|completed|processing|cancelled|active|inactive)\s+(?:orders|items)?",
        query_lower,
    )
    if status_match:
        col = _pick_column(columns, _STATUS_KEYWORDS)
        if col:
            params["status"] = status_match.group(1)
            where_clauses.append(f"{col} = :status")

    # ---------------------------------------------------------------- contains
    contains_match = re.search(
        r"\b(?:with|containing|include)\s+([a-zA-Z\s]+?)(?:\s+(?:where|and|order|limit)|$)",
        query_lower,
    )
    if contains_match:
        value = contains_match.group(1).strip()
        col = _pick_column(columns, _TEXT_KEYWORDS)
        if col and value:
            # The wildcards belong to the pattern, not to the SQL text, so the
            # whole thing is one bound value.
            params["contains"] = f"%{value}%"
            where_clauses.append(f"{col} LIKE :contains")

    if not where_clauses:
        return None

    col_list = ", ".join(columns)
    sql = f"SELECT {col_list} FROM {table_name} " f"WHERE {' AND '.join(where_clauses)} LIMIT 100"
    return sql, params


# ================================================================
# EXECUTION CORE
# ================================================================


def is_safe_select_query(query: str) -> tuple[bool, str]:
    q = query.strip().upper()

    if q.startswith("PRAGMA"):
        return True, ""

    if not q.startswith("SELECT"):
        return False, "Only SELECT queries are allowed."

    if ";" in query:
        return False, "The query contains semicolons, which are not allowed."

    if "--" in query or "/*" in query or "*/" in query:
        return False, "The query contains SQL comments, which are not allowed."

    forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "REPLACE",
        "MERGE",
        "TRUNCATE",
        "ATTACH",
        "DETACH",
    ]

    for k in forbidden:
        if k in q.replace("SELECT", ""):
            return False, f"Query blocked: {k} not permitted."

    return True, ""


def extract_query_identifiers(sql: str) -> tuple[list[str], list[str]]:
    """
    Extract tables + columns from a SELECT query using very simple parsing.
    (LLM-generated queries are simple enough for this to work reliably)
    Ignores SQL functions like EXTRACT(), strftime(), etc.
    """
    sql_clean = sql.replace("\n", " ").replace("\t", " ")

    # Remove SQL functions to avoid extracting function names as columns
    # Common functions: EXTRACT, strftime, DATE, YEAR, MONTH, DAY, etc.
    function_patterns = [
        r"EXTRACT\s*\([^)]*\)",
        r"strftime\s*\([^)]*\)",
        r"DATE\s*\([^)]*\)",
        r"YEAR\s*\([^)]*\)",
        r"MONTH\s*\([^)]*\)",
        r"DAY\s*\([^)]*\)",
        r"COUNT\s*\([^)]*\)",
        r"SUM\s*\([^)]*\)",
        r"AVG\s*\([^)]*\)",
        r"MAX\s*\([^)]*\)",
        r"MIN\s*\([^)]*\)",
    ]
    sql_for_parsing = sql_clean
    for pattern in function_patterns:
        sql_for_parsing = re.sub(pattern, "", sql_for_parsing, flags=re.IGNORECASE)

    # tables from FROM and JOIN clauses
    table_pattern = r"(FROM|JOIN)\s+([A-Za-z0-9_]+)"
    tables = [m[1] for m in re.findall(table_pattern, sql_for_parsing, flags=re.IGNORECASE)]

    # Columns inside SELECT. The FROM is optional so that a query missing its
    # FROM clause still yields columns — that is precisely the input the table
    # inference below exists to repair, and requiring FROM here meant inference
    # never ran for it.
    select_match = re.search(
        r"SELECT(.*?)(?:\bFROM\b|$)", sql_for_parsing, re.IGNORECASE | re.DOTALL
    )
    columns = []
    if select_match:
        col_part = select_match.group(1)
        raw_cols = col_part.split(",")
        for c in raw_cols:
            c = c.strip()
            # Strip an alias before validating the name. This used to run after
            # the loop, by which point "name AS client_name" had already been
            # discarded by the identifier check below — so aliased columns were
            # never extracted and never validated.
            c = re.sub(r"\s+AS\s+.*$", "", c, flags=re.IGNORECASE).strip()

            # Skip if it looks like a function call
            if "(" in c and ")" in c:
                # Try to extract column from inside function (e.g., EXTRACT(MONTH FROM o.order_date))
                # Look for table.column pattern inside
                inner_match = re.search(r"([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)", c)
                if inner_match:
                    columns.append(inner_match.group(2))
                continue
            if "." in c:
                columns.append(c.split(".")[1])
            else:
                # Only add if it's a valid column name (not a function)
                if re.match(r"^[A-Za-z0-9_]+$", c):
                    columns.append(c)

    # drop anything that is not a bare identifier
    columns = [col for col in columns if col and re.match(r"^[A-Za-z0-9_]+$", col)]

    # Also extract any prefixed columns used elsewhere (WHERE, JOIN ON, etc.)
    # e.g. c.city, o.status. Scanned against the original SQL rather than the
    # function-stripped copy: EXTRACT(MONTH FROM o.order_date) is removed wholesale
    # by the stripping above, so scanning the stripped copy meant columns used only
    # inside a function were invisible to validation.
    prefixed = re.findall(r"([A-Za-z0-9_]+)\.([A-Za-z0-9_\*]+)", sql_clean)
    for alias, col in prefixed:
        # ignore table.* patterns here for missing-column checks
        if col == "*":
            continue
        # Only add valid column names (not function calls)
        if re.match(r"^[A-Za-z0-9_]+$", col) and col not in columns:
            columns.append(col)

    return tables, columns


def fuzzy_match(name: str, candidates: list[str]) -> str | None:
    """Fuzzy match a name against candidates. Returns best match if score > 0.4."""
    name_low = name.lower()
    best = None
    best_score = 0.0

    for cand in candidates:
        cand_low = cand.lower()

        # Exact match
        if name_low == cand_low:
            return cand

        # Character overlap score
        char_score = sum(c1 == c2 for c1, c2 in zip(name_low, cand_low)) / max(len(cand_low), 1)

        # Substring match bonus (e.g., "customers" contains "customer" which is close to "clients")
        substring_bonus = 0.0
        if name_low in cand_low or cand_low in name_low:
            substring_bonus = 0.2

        # Common prefix/suffix bonus
        prefix_bonus = 0.0
        suffix_bonus = 0.0
        min_len = min(len(name_low), len(cand_low))
        if min_len >= 3:
            # Check first 3 chars
            if name_low[:3] == cand_low[:3]:
                prefix_bonus = 0.15
            # Check last 3 chars
            if len(name_low) >= 3 and len(cand_low) >= 3 and name_low[-3:] == cand_low[-3:]:
                suffix_bonus = 0.15

        total_score = char_score + substring_bonus + prefix_bonus + suffix_bonus

        if total_score > best_score:
            best_score = total_score
            best = cand

    if best_score > 0.4:
        return best
    return None


def _suggest_column_candidates(
    missing_cols: list[str], schema: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Return fuzzy-matched candidate columns for each missing column."""
    suggestions: dict[str, list[str]] = {}
    all_cols = []
    for cols in schema.values():
        all_cols.extend(cols)

    for mcol in missing_cols:
        cand = []
        # try direct fuzzy match
        match = fuzzy_match(mcol, all_cols)
        if match:
            cand.append(match)
        # also collect close substring matches
        lower = mcol.lower()
        for c in set(all_cols):
            if lower in c.lower() and c not in cand:
                cand.append(c)
        suggestions[mcol] = cand

    return suggestions


def _format_schema_preview(schema: dict[str, list[str]], max_tables: int = 5) -> str:
    """Return a short human-readable preview of the schema for error messages."""
    lines = []
    for i, (tname, cols) in enumerate(schema.items()):
        if i >= max_tables:
            break
        sample = ", ".join(cols[:8])
        lines.append(f"- {tname}: {sample}{'...' if len(cols) > 8 else ''}")
    if len(schema) > max_tables:
        lines.append(f"... and {len(schema) - max_tables} more tables")
    return "\n".join(lines)


def _convert_sqlite_syntax(sql: str) -> str:
    """
    Convert non-SQLite SQL syntax to SQLite-compatible syntax.
    - EXTRACT(MONTH FROM date) -> strftime('%m', date)
    - EXTRACT(YEAR FROM date) -> strftime('%Y', date)
    - EXTRACT(DAY FROM date) -> strftime('%d', date)
    """

    # Convert EXTRACT(MONTH FROM ...) to strftime('%m', ...)
    def extract_to_strftime(match):
        extract_type = match.group(1).upper()
        date_expr = match.group(2)
        if extract_type == "MONTH":
            return f"CAST(strftime('%m', {date_expr}) AS INTEGER)"
        elif extract_type == "YEAR":
            return f"CAST(strftime('%Y', {date_expr}) AS INTEGER)"
        elif extract_type == "DAY":
            return f"CAST(strftime('%d', {date_expr}) AS INTEGER)"
        else:
            # Generic conversion
            return f"strftime('%{extract_type[0]}', {date_expr})"

    # Pattern: EXTRACT(MONTH FROM o.order_date) or EXTRACT (MONTH FROM o.order_date)
    sql = re.sub(
        r"EXTRACT\s*\(\s*(\w+)\s+FROM\s+([^)]+)\s*\)", extract_to_strftime, sql, flags=re.IGNORECASE
    )

    return sql


def validate_and_fix_sql(sql: str, schema: dict[str, list[str]]) -> tuple[bool, str, str]:
    """
    Validate SQL against a database schema and fix table/column names when possible.

    The schema is injected rather than read from a module-global sqlite connection,
    which is what makes this function pure: it is synchronous, has no side effects,
    works against any dialect, and can be tested without a database.

    Dialect translation is deliberately *not* done here. _convert_sqlite_syntax
    rewrites EXTRACT() into strftime(), which is correct for sqlite and wrong for
    postgres, so the caller applies it only when the connection is sqlite.

    Args:
        sql: The query to validate, typically LLM-generated.
        schema: Mapping of table name to its column names.

    Returns:
        (success: bool, message: str, fixed_sql: str)
    """
    if not schema:
        return False, "Database schema is empty.", sql

    fixed_sql = sql

    # We'll attempt up to N iterations to validate and auto-correct the SQL.
    # Only after exhausting all attempts will we return an error.
    max_attempts = 10

    for attempt in range(1, max_attempts + 1):
        tables, columns = extract_query_identifiers(fixed_sql)

        # If the SELECT clause contains no column names, handle two cases:
        # - empty SELECT clause -> return an error asking for explicit columns
        # - SELECT * -> treat as valid and continue
        if not columns:
            select_only = re.search(
                r"SELECT\s*(.*?)\s*(FROM|$)", fixed_sql, flags=re.IGNORECASE | re.DOTALL
            )
            select_part = select_only.group(1).strip() if select_only else ""
            if select_part == "":
                return (
                    False,
                    (
                        "No column names were specified in the SELECT clause. "
                        "Please list the columns you want (for example: SELECT c.name, o.order_date ...)"
                    ),
                    sql,
                )
            if select_part == "*":
                # Accept SELECT * as a valid selector; represent it explicitly
                columns = ["*"]

        # Immediate check: if any referenced column does not exist in the entire
        # database schema, fail early and inform the caller with suggestions.
        # Ignore wildcard '*' when checking column existence
        missing_cols = [
            c for c in columns if c != "*" and not any(c in cols for cols in schema.values())
        ]
        if missing_cols:
            suggestions = _suggest_column_candidates(missing_cols, schema)
            suggestion_texts = []
            for mcol in missing_cols:
                cand = suggestions.get(mcol, [])
                if cand:
                    suggestion_texts.append(f"'{mcol}' -> did you mean: {', '.join(cand)}")
                else:
                    suggestion_texts.append(f"'{mcol}' -> no similar column found")

            schema_preview = _format_schema_preview(schema)
            msg = (
                f"Column(s) not found in schema: {', '.join(missing_cols)}. "
                f"Suggestions: {'; '.join(suggestion_texts)}\n\n"
                "Schema preview:\n" + schema_preview + "\n\n"
                "Please update your query to use existing column names."
            )
            return False, msg, sql

        # 1) Try to infer tables and FROM/JOIN if none found but columns exist
        if not tables and columns:
            inferred = []
            for col in columns:
                for tname, cols in schema.items():
                    if col in cols and tname not in inferred:
                        inferred.append(tname)

            if inferred:
                aliases = {t: f"t{i + 1}" for i, t in enumerate(inferred)}
                base = inferred[0]
                from_clause = f"FROM {base} {aliases[base]}"
                failed = False

                for other in inferred[1:]:
                    common = set(schema[base]).intersection(schema[other])
                    join_col = None
                    for c in common:
                        if c.endswith("_id") or c == "id":
                            join_col = c
                            break

                    if not join_col and common:
                        join_col = next(iter(common))

                    if not join_col:
                        failed = True
                        break

                    from_clause += (
                        f" JOIN {other} {aliases[other]} ON "
                        f"{aliases[base]}.{join_col} = {aliases[other]}.{join_col}"
                    )

                if not failed:
                    m = re.search(
                        r"(SELECT\s+.*?)(WHERE|GROUP BY|ORDER BY|LIMIT|$)",
                        fixed_sql,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    if m:
                        select_part = m.group(1).strip()
                        rest = fixed_sql[m.end(1) :]
                        fixed_sql = select_part + " " + from_clause + rest
                    else:
                        fixed_sql = fixed_sql.rstrip().rstrip(";") + " " + from_clause + ";"
                else:
                    # cannot infer joins between inferred tables; mark as no change
                    pass

                # Continue to next iteration to re-extract identifiers

        # 2) Validate table names, allowing fuzzy fixes
        tables, columns = extract_query_identifiers(fixed_sql)
        final_tables = {}
        changed = False

        for t in tables:
            if t in schema:
                final_tables[t] = t
            else:
                match = fuzzy_match(t, list(schema.keys()))
                if match:
                    final_tables[t] = match
                    # replace table name in SQL
                    fixed_sql = re.sub(rf"\b{t}\b", match, fixed_sql)
                    changed = True
                else:
                    final_tables[t] = t  # keep as-is for now

        # 3) Validate columns: do NOT auto-replace column names. If any referenced
        # column does not exist in the schema, return an explicit, alias-aware
        # error asking for clarification and providing suggestions.
        tables, columns = extract_query_identifiers(fixed_sql)

        # Build alias -> table mapping from FROM/JOIN clauses
        alias_map: dict[str, str] = {}
        from_join_pattern = r"(FROM|JOIN)\s+([A-Za-z0-9_]+)(?:\s+([A-Za-z0-9_]+))?"
        for from_join in re.findall(from_join_pattern, fixed_sql, flags=re.IGNORECASE):
            tbl = from_join[1]
            alias = from_join[2] if len(from_join) > 2 and from_join[2] else None
            if alias:
                alias_map[alias] = tbl

        # Detect prefixed columns like alias.col to give table-specific messages
        prefixed_cols = re.findall(r"([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)", fixed_sql)
        pref_map = {col: alias for alias, col in prefixed_cols}

        # Pairs of (column, table) — distinct from the plain name list above,
        # which reused the same variable name for a different element type.
        missing_pairs: list[tuple[str, str | None]] = []
        for col in columns:
            # Treat wildcard '*' as valid — skip further column existence checks
            if col == "*":
                continue

            # If prefixed, map to the table indicated
            if col in pref_map:
                alias = pref_map[col]
                tbl = alias_map.get(alias)
                if tbl and col not in schema.get(tbl, []):
                    missing_pairs.append((col, tbl))
                # if table not resolvable, treat as global check below
            else:
                # global check across schema
                if not any(col in cols for cols in schema.values()):
                    missing_pairs.append((col, None))

        if missing_pairs:
            # Prepare suggestions per missing column
            cols_only = [c for c, _ in missing_pairs]
            suggestions = _suggest_column_candidates(cols_only, schema)
            parts = []
            for c, tbl in missing_pairs:
                cand = suggestions.get(c, [])
                if tbl:
                    if cand:
                        parts.append(
                            f"Column '{c}' not found in table '{tbl}'. Suggestions: {', '.join(cand)}"
                        )
                    else:
                        parts.append(
                            f"Column '{c}' not found in table '{tbl}'. No similar column found."
                        )
                else:
                    if cand:
                        parts.append(
                            f"Column '{c}' not found in any table. Suggestions: {', '.join(cand)}"
                        )
                    else:
                        parts.append(f"Column '{c}' not found in any table.")

            schema_preview = _format_schema_preview(schema)
            msg = (
                "The query references columns that don't match your database schema.\n"
                + "\n".join(parts)
                + "\n\nSchema preview:\n"
                + schema_preview
                + "\n\nPlease clarify which columns you intended to use."
            )
            return False, msg, sql

        # 4) If no referenced tables were detected at all, we may still try broader fuzzy
        # matching by checking columns across the whole schema and adding suggestions.
        if not tables and columns:
            # attempt a lightweight infer by adding single table that contains most columns
            score_map = {}
            for tname, cols in schema.items():
                score_map[tname] = sum(1 for c in columns if c in cols)
            best_table = max(score_map, key=score_map.get)
            if score_map[best_table] > 0:
                # append FROM best_table
                if "FROM" not in fixed_sql.upper():
                    fixed_sql = fixed_sql.rstrip().rstrip(";") + f" FROM {best_table};"
                    changed = True

        # 5) If we made changes, try another iteration; if not, decide if valid
        tables, columns = extract_query_identifiers(fixed_sql)

        # Check whether all referenced tables exist in schema
        all_tables_valid = True
        if tables:
            for t in tables:
                if t not in schema:
                    all_tables_valid = False
                    break

        # Check whether all referenced columns exist in their tables
        all_columns_valid = True
        if columns and tables:
            for col in columns:
                # Treat wildcard '*' as valid
                if col == "*":
                    continue
                col_found = any(col in schema.get(t, []) for t in tables)
                if not col_found:
                    all_columns_valid = False
                    break

        if all_tables_valid and (not columns or all_columns_valid):
            # Final table-name normalization (fuzzy replacements already applied)
            return True, "Corrected SQL", fixed_sql

        # If this was the last attempt, return a helpful error
        if attempt == max_attempts:
            return False, _unresolved_tables_message(tables, schema), fixed_sql

        # Nothing changed this iteration, so further attempts would repeat the
        # same work on the same string. Stop rather than spin out the remaining
        # attempts. (The original looped over schema keys doing nothing here.)
        if not changed:
            break

    return False, _unresolved_tables_message(tables, schema), fixed_sql


def _unresolved_tables_message(tables: list[str], schema: dict[str, list[str]]) -> str:
    """Explain which tables could not be resolved, and show what does exist.

    Replaces a bare "Unable to validate SQL." The common way to reach here is a
    table name that is not a typo of a real one — `customers` against a schema
    whose table is `clients`. No string-distance matcher can bridge that, and
    guessing would silently query the wrong table, so the caller is told plainly
    what was not found and what is available.
    """
    unknown = [t for t in tables if t not in schema]
    if not unknown:
        return (
            "Could not validate the query against the schema.\n\nSchema preview:\n"
            + _format_schema_preview(schema)
        )

    parts = []
    for table in unknown:
        match = fuzzy_match(table, list(schema.keys()))
        if match:
            parts.append(f"Table '{table}' not found. Did you mean '{match}'?")
        else:
            parts.append(f"Table '{table}' not found in the schema.")

    return (
        "The query references tables that do not exist.\n"
        + "\n".join(parts)
        + "\n\nSchema preview:\n"
        + _format_schema_preview(schema)
        + "\n\nPlease use one of the tables above."
    )
