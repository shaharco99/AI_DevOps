"""
Improved database tools for LLM agent:
✔ SELECT-only enforcement
✔ Auto-preview only when necessary
✔ Auto-correct SQL queries based on DB schema
✔ Auto-detect invalid table/column names
✔ Schema-aware SQL validation before execution
✔ SQLite schema fix (shared connection)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain.tools import tool

_db_config: Optional[Dict[str, Any]] = None
_db_connection = None

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


# ================================================================
# CONFIG + CONNECTION
# ================================================================

def load_db_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    global _db_config
    if _db_config:
        return _db_config

    if config_file is None:
        config_file = os.getenv('DB_CONFIG_FILE', 'db_config.json')

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                _db_config = json.load(f)
                return _db_config
        except Exception:
            pass

    db_type = os.getenv('DB_TYPE', 'sqlite').lower()

    if db_type == 'sqlite':
        _db_config = {
            'type': 'sqlite',
            'database': os.getenv('DB_PATH', 'sample_database.db'),
            'use_uri': os.getenv('DB_USE_URI', 'false').lower() in ('1', 'true', 'yes')
        }
    else:
        raise ValueError('Only sqlite is supported in this configuration')

    return _db_config


def get_db_connection():
    global _db_connection

    if _db_connection:
        return _db_connection

    config = load_db_config()
    db_type = config['type']

    if db_type == 'sqlite':
        # Prevent accidental creation of a new sqlite file when path is wrong.
        # Resolve the configured path and ensure it exists before connecting.
        present, db_path = _is_db_file_present()
        if not present:
            raise FileNotFoundError(
                'Configured SQLite DB not found. Check DB_PATH in your .env file. '
                f"Configured path: {db_path or config.get('database')}"
            )

        import sqlite3
        use_uri = config.get('use_uri', False)
        conn = sqlite3.connect(db_path, check_same_thread=False, uri=use_uri)
        conn.row_factory = sqlite3.Row
        _db_connection = conn
        return conn

    raise ValueError('Unsupported DB type')


def close_db_connection():
    global _db_connection
    if _db_connection:
        try:
            _db_connection.close()
        except Exception:
            pass
        _db_connection = None


# ================================================================
# EXECUTION CORE
# ================================================================

def execute_query(query: str, params=None):
    """
    Executes SQL and returns (results, error)
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)

        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            return rows, None

        return [], None

    except Exception as e:
        return [], str(e)


# ================================================================
# SCHEMA EXTRACTION
# ================================================================

def get_sqlite_schema() -> Dict[str, List[str]]:
    """
    Returns schema as:
    {
        "table_name": ["col1", "col2", ...],
        ...
    }
    """
    schema = {}

    # get all tables & views
    tables, err = execute_query("SELECT name FROM sqlite_master WHERE type IN ('table','view');")
    if err:
        return {}

    for row in tables:
        tname = row['name']
        cols, _ = execute_query(f"PRAGMA table_info('{tname}');")
        schema[tname] = [c['name'] for c in cols]

    return schema


def get_database_schema() -> str:
    schema = get_sqlite_schema()
    if not schema:
        return 'No tables or views found.'

    lines = []
    for table, cols in schema.items():
        col_info = ', '.join(cols)
        lines.append(f"Table '{table}': {col_info}")

    return '\n'.join(lines)


def _resolve_sqlite_path() -> Optional[str]:
    """Return resolved filesystem path for the configured sqlite database, or None."""
    cfg = load_db_config()
    if not cfg or cfg.get('type') != 'sqlite':
        return None
    db_path = cfg.get('database')
    if not db_path:
        return None
    # Normalize input path
    db_path = os.path.expanduser(db_path)
    db_path = os.path.normpath(db_path)

    candidates = []
    # If absolute, that's the primary candidate
    if os.path.isabs(db_path):
        candidates.append(db_path)
    else:
        # 1) As provided relative to current working directory
        candidates.append(os.path.join(os.getcwd(), db_path))
        # 2) Relative to this module's directory (useful when DB placed in LLM_CI/)
        module_dir = os.path.dirname(__file__)
        candidates.append(os.path.join(module_dir, db_path))
        # 3) One level up from module (repo root) — in many samples the DB lives in repo root
        candidates.append(os.path.normpath(os.path.join(module_dir, '..', db_path)))

    # Normalize candidate paths and return the first one that exists
    normalized = [os.path.normpath(p) for p in candidates]
    for p in normalized:
        if os.path.exists(p):
            return p

    # If none exist, return the first normalized candidate (so error messages show a meaningful path)
    return normalized[0] if normalized else os.path.normpath(db_path)


def _is_db_file_present() -> Tuple[bool, str]:
    """Check whether the configured DB file exists. Returns (present, path)."""
    path = _resolve_sqlite_path()
    if not path:
        return False, ''
    return (os.path.exists(path), path)


# ================================================================
# SQL VALIDATION + AUTO-CORRECTION
# ================================================================

def is_safe_select_query(query: str) -> Tuple[bool, str]:
    q = query.strip().upper()

    if q.startswith('PRAGMA'):
        return True, ''

    if not q.startswith('SELECT'):
        return False, 'Only SELECT queries are allowed.'

    if ';' in query:
        return False, 'The query contains semicolons, which are not allowed.'

    if '--' in query or '/*' in query or '*/' in query:
        return False, 'The query contains SQL comments, which are not allowed.'

    forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
                 'REPLACE', 'MERGE', 'TRUNCATE', 'ATTACH', 'DETACH']

    for k in forbidden:
        if k in q.replace('SELECT', ''):
            return False, f"Query blocked: {k} not permitted."

    return True, ''


def extract_query_identifiers(sql: str) -> Tuple[List[str], List[str]]:
    """
    Extract tables + columns from a SELECT query using very simple parsing.
    (LLM-generated queries are simple enough for this to work reliably)
    """
    sql_clean = sql.replace('\n', ' ').replace('\t', ' ')

    # tables from FROM and JOIN clauses
    table_pattern = r'(FROM|JOIN)\s+([A-Za-z0-9_]+)'
    tables = [m[1] for m in re.findall(table_pattern, sql_clean, flags=re.IGNORECASE)]

    # columns inside SELECT
    select_match = re.search(r'SELECT(.*?)FROM', sql_clean, re.IGNORECASE)
    columns = []
    if select_match:
        col_part = select_match.group(1)
        raw_cols = col_part.split(',')
        for c in raw_cols:
            c = c.strip()
            if '.' in c:
                columns.append(c.split('.')[1])
            else:
                columns.append(c)

    # clean column aliases
    columns = [re.sub(r'\s+AS\s+.*', '', col, flags=re.IGNORECASE) for col in columns]
    columns = [col for col in columns if col]

    # Also extract any prefixed columns used elsewhere (WHERE, JOIN ON, etc.)
    # e.g. c.city, o.status
    prefixed = re.findall(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_\*]+)', sql)
    for alias, col in prefixed:
        # ignore table.* patterns here for missing-column checks
        if col == '*':
            continue
        if col not in columns:
            columns.append(col)

    return tables, columns


def fuzzy_match(name: str, candidates: List[str]) -> Optional[str]:
    name_low = name.lower()
    best = None
    best_score = 0

    for cand in candidates:
        cand_low = cand.lower()
        score = sum(c1 == c2 for c1, c2 in zip(name_low, cand_low)) / max(len(cand_low), 1)

        if score > best_score:
            best_score = score
            best = cand

    if best_score > 0.4:
        return best
    return None


def _suggest_column_candidates(missing_cols: List[str], schema: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Return fuzzy-matched candidate columns for each missing column."""
    suggestions: Dict[str, List[str]] = {}
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


def _format_schema_preview(schema: Dict[str, List[str]], max_tables: int = 5) -> str:
    """Return a short human-readable preview of the schema for error messages."""
    lines = []
    for i, (tname, cols) in enumerate(schema.items()):
        if i >= max_tables:
            break
        sample = ', '.join(cols[:8])
        lines.append(f"- {tname}: {sample}{'...' if len(cols) > 8 else ''}")
    if len(schema) > max_tables:
        lines.append(f"... and {len(schema) - max_tables} more tables")
    return '\n'.join(lines)


def validate_and_fix_sql(sql: str) -> Tuple[bool, str, str]:
    """
    Validate SQL against the DB schema and fix table/column names when possible.

    Returns:
        (success: bool, message: str, fixed_sql: str)
    """
    # If the configured DB file is missing, bail early with a clear message
    present, db_path = _is_db_file_present()
    if not present:
        example = os.path.join(os.getcwd(), 'LLM_CI', 'sample_database.db')
        example_unix = example.replace('\\', '/')
        return False, (
            'no DB found — please check `DB_PATH` in your .env file. '
            f"Example: DB_PATH={example_unix}"
        ), sql

    schema = get_sqlite_schema()
    if not schema:
        return False, 'Database schema is empty.', sql

    # We'll attempt up to N iterations to validate and auto-correct the SQL.
    # Only after exhausting all attempts will we return an error.
    max_attempts = 10
    fixed_sql = sql

    for attempt in range(1, max_attempts + 1):
        tables, columns = extract_query_identifiers(fixed_sql)

        # If the SELECT clause contains no column names, handle two cases:
        # - empty SELECT clause -> return an error asking for explicit columns
        # - SELECT * -> treat as valid and continue
        if not columns:
            select_only = re.search(r'SELECT\s*(.*?)\s*(FROM|$)', fixed_sql, flags=re.IGNORECASE | re.DOTALL)
            select_part = select_only.group(1).strip() if select_only else ''
            if select_part == '':
                return False, (
                    'No column names were specified in the SELECT clause. '
                    'Please list the columns you want (for example: SELECT c.name, o.order_date ...)'), sql
            if select_part == '*':
                # Accept SELECT * as a valid selector; represent it explicitly
                columns = ['*']

        # Immediate check: if any referenced column does not exist in the entire
        # database schema, fail early and inform the caller with suggestions.
        # Ignore wildcard '*' when checking column existence
        missing_cols = [c for c in columns if c != '*' and not any(c in cols for cols in schema.values())]
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
                'Schema preview:\n' + schema_preview + '\n\n'
                'Please update your query to use existing column names.'
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
                        if c.endswith('_id') or c == 'id':
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
                    m = re.search(r'(SELECT\s+.*?)(WHERE|GROUP BY|ORDER BY|LIMIT|$)', fixed_sql, flags=re.IGNORECASE | re.DOTALL)
                    if m:
                        select_part = m.group(1).strip()
                        rest = fixed_sql[m.end(1):]
                        fixed_sql = select_part + ' ' + from_clause + rest
                    else:
                        fixed_sql = fixed_sql.rstrip().rstrip(';') + ' ' + from_clause + ';'
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
        alias_map: Dict[str, str] = {}
        from_join_pattern = r'(FROM|JOIN)\s+([A-Za-z0-9_]+)(?:\s+([A-Za-z0-9_]+))?'
        for m in re.findall(from_join_pattern, fixed_sql, flags=re.IGNORECASE):
            tbl = m[1]
            alias = m[2] if len(m) > 2 and m[2] else None
            if alias:
                alias_map[alias] = tbl

        # Detect prefixed columns like alias.col to give table-specific messages
        prefixed_cols = re.findall(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)', fixed_sql)
        pref_map = {col: alias for alias, col in prefixed_cols}

        missing_cols = []
        for col in columns:
            # Treat wildcard '*' as valid — skip further column existence checks
            if col == '*':
                continue

            # If prefixed, map to the table indicated
            if col in pref_map:
                alias = pref_map[col]
                tbl = alias_map.get(alias)
                if tbl and col not in schema.get(tbl, []):
                    missing_cols.append((col, tbl))
                # if table not resolvable, treat as global check below
            else:
                # global check across schema
                if not any(col in cols for cols in schema.values()):
                    missing_cols.append((col, None))

        if missing_cols:
            # Prepare suggestions per missing column
            cols_only = [c for c, _ in missing_cols]
            suggestions = _suggest_column_candidates(cols_only, schema)
            parts = []
            for c, tbl in missing_cols:
                cand = suggestions.get(c, [])
                if tbl:
                    if cand:
                        parts.append(f"Column '{c}' not found in table '{tbl}'. Suggestions: {', '.join(cand)}")
                    else:
                        parts.append(f"Column '{c}' not found in table '{tbl}'. No similar column found.")
                else:
                    if cand:
                        parts.append(f"Column '{c}' not found in any table. Suggestions: {', '.join(cand)}")
                    else:
                        parts.append(f"Column '{c}' not found in any table.")

            schema_preview = _format_schema_preview(schema)
            msg = (
                "The query references columns that don't match your database schema.\n"
                + '\n'.join(parts)
                + '\n\nSchema preview:\n'
                + schema_preview
                + '\n\nPlease clarify which columns you intended to use.'
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
                if 'FROM' not in fixed_sql.upper():
                    fixed_sql = fixed_sql.rstrip().rstrip(';') + f" FROM {best_table};"
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
                if col == '*':
                    continue
                col_found = any(col in schema.get(t, []) for t in tables)
                if not col_found:
                    all_columns_valid = False
                    break

        if all_tables_valid and (not columns or all_columns_valid):
            # Final table-name normalization (fuzzy replacements already applied)
            return True, 'Corrected SQL', fixed_sql

        # If this was the last attempt, return a helpful error
        if attempt == max_attempts:
            return False, f"Could not construct valid SQL after {max_attempts} attempts.", fixed_sql

        # If nothing changed this iteration, continue to next attempt but avoid infinite loop
        if not changed:
            # small heuristic: try to be more aggressive by attempting broad fuzzy on table names
            for tname in list(schema.keys()):
                # no-op placeholder to allow next iteration
                pass

    # Fallback
    return False, 'Unable to validate SQL.', fixed_sql


# ================================================================
# Retrieval-Augmented Generation (RAG) helpers
# The functions below expect an `llm_callable(prompt: str) -> str` which
# returns the LLM's text response. We keep the LLM dependency out of this
# module to avoid importing third-party libraries here; the caller should
# pass a small wrapper that calls the configured LLM.
# ================================================================


def _get_table_preview(table: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return a few sample rows from `table` for context (empty list on error)."""
    try:
        rows, err = execute_query(f"SELECT * FROM {table} LIMIT {limit}")
        if err:
            return []
        return rows
    except Exception:
        return []


def _is_suspicious_filter(sql: str, schema: Dict[str, List[str]]) -> Tuple[bool, str]:
    """Detect filters that are likely ambiguous (e.g. two-letter token used against `country`).

    Returns (is_suspicious, reason)
    """
    # simple heuristic: if SQL compares country/state to a short token (len<=3), flag it
    m = re.findall(r"([A-Za-z0-9_\.]+)\s*=\s*'([^']+)'", sql)
    for left, val in m:
        # strip alias if present
        if '.' in left:
            _, col = left.split('.', 1)
        else:
            col = left
        lower = col.lower()
        # Relaxed heuristic: only flag very short tokens (<=2). This avoids
        # flagging common 3-letter country codes like 'USA'. If you want
        # stricter checks in the future, consider a configurable policy.
        if lower in ('country', 'state') and len(val.strip()) <= 2:
            return True, f"Filter {col} = '{val}' looks ambiguous: very short token against {col}."
    return False, ''


def generate_sql_with_rag(
    user_question: str,
    llm_callable: Callable[[str], str],
    max_attempts: int = 3,
    include_schema_preview: bool = True,
) -> Tuple[bool, str, str]:
    """Generate a SQL statement for `user_question` using a RAG approach.

    - `llm_callable` should accept a plain-text prompt and return text.
    - The function will provide schema + examples, ask the LLM to return ONLY SQL,
      then validate using `validate_and_fix_sql`.
    - On validation failure the function will retry up to `max_attempts`.

    Returns (success, message, sql_or_error_message)
    """
    schema = get_sqlite_schema()
    if not schema:
        return False, 'Database schema is empty.', user_question

    # Build context
    schema_text_lines = []
    for t, cols in schema.items():
        schema_text_lines.append(f"{t}({', '.join(cols)})")
    schema_text = '\n'.join(schema_text_lines[:50])

    # Add small previews for top tables
    previews = []
    for t in list(schema.keys())[:3]:
        rows = _get_table_preview(t, limit=3)
        if rows:
            previews.append(f"Sample rows from {t}: {rows}")

    base_prompt = (
        'You are given a database schema and a user question. '
        'Return ONLY a single valid SELECT SQL query that answers the question. '
        "DO NOT include any explanation. If you cannot produce a valid SQL, reply with 'CANNOT_GENERATE'.\n\n"
        f"Schema:\n{schema_text}\n\n"
    )
    if include_schema_preview and previews:
        base_prompt += '\n'.join(previews) + '\n\n'

    base_prompt += f"User question: {user_question}\n\nSQL:"

    last_error = ''
    last_candidate = ''
    for attempt in range(1, max_attempts + 1):
        try:
            llm_resp = llm_callable(base_prompt)
        except Exception as e:
            return False, f"LLM call failed: {e}", ''

        if not llm_resp or 'CANNOT_GENERATE' in llm_resp.upper():
            last_error = 'LLM refused to generate SQL.'
            continue

        # Extract first SQL-looking block
        sql_candidate = llm_resp.strip().split(';')[0].strip()
        last_candidate = sql_candidate
        if not sql_candidate.upper().startswith('SELECT'):
            last_error = 'LLM did not return a SELECT statement.'
            continue

        # Validate candidate
        is_valid, msg, fixed_sql = validate_and_fix_sql(sql_candidate)
        if is_valid:
            # Check for suspicious filters
            suspicious, reason = _is_suspicious_filter(fixed_sql, schema)
            if suspicious:
                return False, f"Suspicious filter detected: {reason} Please clarify.", fixed_sql

            return True, 'OK', fixed_sql

        # Provide the validation feedback to LLM and retry
        base_prompt += f"\n-- Validation feedback: {msg}\nPlease return ONLY a corrected SQL or CANNOT_GENERATE.\nSQL:"
        last_error = msg

    # If we exhausted attempts but have a last candidate, return it for manual review
    if last_candidate:
        return False, f"Could not generate valid SQL: {last_error}", last_candidate

    return False, f"Could not generate valid SQL: {last_error}", ''


def rag_query_and_execute(
    user_question: str,
    llm_callable: Callable[[str], str],
    auto_execute: bool = False,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """High-level function: use RAG to generate SQL and optionally execute it.

    Returns a dict with keys: `success` (bool), `sql` (str), `message` (str), `results` (list)
    """
    ok, msg, sql = generate_sql_with_rag(user_question, llm_callable, max_attempts=max_attempts)
    if not ok:
        # If a SQL candidate was returned despite validation failure, surface it for preview/repair
        if sql:
            return {'success': True, 'sql': sql, 'message': f'{msg} (validation failed; please review before executing)', 'results': []}
        return {'success': False, 'sql': '', 'message': msg, 'results': []}

    # If not auto_execute, return SQL for approval
    if not auto_execute:
        return {'success': True, 'sql': sql, 'message': 'SQL generated; approval required to execute.', 'results': []}

    # Execute safely
    present, _ = _is_db_file_present()
    if not present:
        return {'success': False, 'sql': sql, 'message': 'Database file not found.', 'results': []}

    rows, err = execute_query(sql)
    if err:
        return {'success': False, 'sql': sql, 'message': f'Execution error: {err}', 'results': []}

    return {'success': True, 'sql': sql, 'message': 'Executed successfully.', 'results': rows}


# ================================================================
# TOOLS FOR AGENT
# ================================================================

@tool
def generate_and_preview_query(user_question: str) -> str:
    """
    Agent calls this when it needs help constructing a correct SQL SELECT query.
    Does NOT force preview. Execution can happen directly if agent is confident.
    """
    sanitized_question = user_question.replace("'", "''")

    try:
        schema = get_database_schema()
    except Exception as e:
        schema = f"Schema unavailable: {e}"

    return (
        f"User question: {sanitized_question}\n\n"
        f"Database Schema:\n{schema}\n\n"
        f"Generate a SINGLE valid SELECT query that answers the question.\n"
        f"No mutations allowed. Return ONLY the SQL, no explanations."
    )


@tool
def execute_database_query(sql_query: str) -> str:
    """
    Executes ONLY a SELECT / PRAGMA query after validating and correcting it.
    """
    # 1) Safety rule
    ok, msg = is_safe_select_query(sql_query)
    if not ok:
        return json.dumps({'error': msg, 'query': sql_query, 'results': []})

    # 2) Validate against schema and auto-fix if needed
    is_valid, msg, fixed_sql = validate_and_fix_sql(sql_query)
    if not is_valid:
        return json.dumps({'error': msg, 'query': sql_query, 'results': []})

    # 3) Execute corrected SQL
    results, err = execute_query(fixed_sql)
    if err:
        return json.dumps({'error': err, 'query': fixed_sql, 'results': []})

    return json.dumps({
        'success': True,
        'query': fixed_sql,
        'row_count': len(results),
        'results': results
    })
