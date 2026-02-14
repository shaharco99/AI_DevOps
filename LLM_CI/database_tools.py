"""
Database tools for AI agents:
✔ SELECT-only enforcement
✔ Auto-correct SQL queries based on DB schema
✔ Auto-detect invalid table/column names
✔ Schema-aware SQL validation before execution
✔ SQLite schema fix (shared connection)
✔ All functions exposed as @tool decorated functions for AI agent use
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from langchain.tools import tool
except Exception:
    tool = None

_db_config: Optional[Dict[str, Any]] = None
_db_connection = None

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

_engine = None

try:
    from sqlalchemy import create_engine, text as sa_text
except Exception:
    create_engine = None
    sa_text = None


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
    elif db_type in ('postgresql', 'postgres'):
        _db_config = {
            'type': 'postgresql',
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', ''),
        }
    elif db_type in ('mysql',):
        _db_config = {
            'type': 'mysql',
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', ''),
        }
    elif db_type in ('mssql', 'sqlserver'):
        _db_config = {
            'type': 'mssql',
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 1433)),
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', ''),
            'driver': os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
        }
    else:
        raise ValueError(f'Unsupported DB_TYPE: {db_type}')

    return _db_config


def _build_sqlalchemy_url(cfg: Dict[str, Any]) -> Optional[str]:
    """Construct a SQLAlchemy URL from the loaded config, if possible."""
    if not create_engine:
        return None

    t = cfg.get('type')
    if t == 'sqlite':
        db_path = cfg.get('database')
        if not db_path:
            return None
        db_path = os.path.expanduser(db_path)
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.getcwd(), db_path)
        return f"sqlite:///{db_path}"

    if t == 'postgresql':
        user = cfg.get('user', '')
        password = cfg.get('password', '')
        host = cfg.get('host', 'localhost')
        port = cfg.get('port', 5432)
        db = cfg.get('database', '')
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

    if t == 'mysql':
        user = cfg.get('user', '')
        password = cfg.get('password', '')
        host = cfg.get('host', 'localhost')
        port = cfg.get('port', 3306)
        db = cfg.get('database', '')
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"

    if t == 'mssql':
        user = cfg.get('user', '')
        password = cfg.get('password', '')
        host = cfg.get('host', 'localhost')
        port = cfg.get('port', 1433)
        db = cfg.get('database', '')
        driver = cfg.get('driver', 'ODBC Driver 17 for SQL Server')
        from urllib.parse import quote_plus
        odbc_str = f"DRIVER={{{driver}}};SERVER={host},{port};DATABASE={db};UID={user};PWD={password}"
        params = quote_plus(odbc_str)
        return f"mssql+pyodbc:///?odbc_connect={params}"

    return None


def get_engine():
    """Return a SQLAlchemy engine if available and configured."""
    global _engine
    if _engine is not None:
        return _engine

    if not create_engine:
        return None

    cfg = load_db_config()
    url = _build_sqlalchemy_url(cfg)
    if not url:
        return None

    try:
        _engine = create_engine(url, future=True)
        return _engine
    except Exception:
        return None


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

    # Postgres via psycopg2
    if db_type == 'postgresql':
        try:
            import psycopg2
        except Exception as e:
            raise ImportError('psycopg2 is required for PostgreSQL connections') from e

        conn = psycopg2.connect(
            host=config.get('host'),
            port=config.get('port'),
            user=config.get('user'),
            password=config.get('password'),
            dbname=config.get('database')
        )
        _db_connection = conn
        return conn

    # MySQL via PyMySQL
    if db_type == 'mysql':
        try:
            import pymysql
        except Exception as e:
            raise ImportError('pymysql is required for MySQL connections') from e

        conn = pymysql.connect(
            host=config.get('host'),
            port=int(config.get('port', 3306)),
            user=config.get('user'),
            password=config.get('password'),
            db=config.get('database'),
            cursorclass=None,
            charset='utf8mb4'
        )
        _db_connection = conn
        return conn

    # MSSQL via pyodbc
    if db_type == 'mssql':
        try:
            import pyodbc
        except Exception as e:
            raise ImportError('pyodbc is required for MSSQL connections') from e

        driver = config.get('driver')
        host = config.get('host')
        port = config.get('port')
        database = config.get('database')
        user = config.get('user')
        password = config.get('password')

        conn_str = (
            f'DRIVER={{{driver}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password}'
        )
        conn = pyodbc.connect(conn_str)
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
    # Prefer SQLAlchemy engine if available for unified behavior
    try:
        engine = get_engine()
        if engine is not None:
            try:
                conn = engine.connect()
                if sa_text is not None:
                    result = conn.execute(sa_text(query))
                else:
                    result = conn.execute(query)
                rows = []
                try:
                    for r in result:
                        # SQLAlchemy 1.4 Row objects expose _mapping
                        if hasattr(r, '_mapping'):
                            rows.append(dict(r._mapping))
                        else:
                            rows.append(dict(r))
                except Exception:
                    # No rows
                    rows = []
                conn.close()
                return rows, None
            except Exception as e:
                # Fall back to DB-API path below
                LOG.warning(f"SQLAlchemy execution failed, falling back: {e}")

        # DB-API fallback
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
    Ignores SQL functions like EXTRACT(), strftime(), etc.
    """
    sql_clean = sql.replace('\n', ' ').replace('\t', ' ')

    # Remove SQL functions to avoid extracting function names as columns
    # Common functions: EXTRACT, strftime, DATE, YEAR, MONTH, DAY, etc.
    function_patterns = [
        r'EXTRACT\s*\([^)]*\)',
        r'strftime\s*\([^)]*\)',
        r'DATE\s*\([^)]*\)',
        r'YEAR\s*\([^)]*\)',
        r'MONTH\s*\([^)]*\)',
        r'DAY\s*\([^)]*\)',
        r'COUNT\s*\([^)]*\)',
        r'SUM\s*\([^)]*\)',
        r'AVG\s*\([^)]*\)',
        r'MAX\s*\([^)]*\)',
        r'MIN\s*\([^)]*\)',
    ]
    sql_for_parsing = sql_clean
    for pattern in function_patterns:
        sql_for_parsing = re.sub(pattern, '', sql_for_parsing, flags=re.IGNORECASE)

    # tables from FROM and JOIN clauses
    table_pattern = r'(FROM|JOIN)\s+([A-Za-z0-9_]+)'
    tables = [m[1] for m in re.findall(table_pattern, sql_for_parsing, flags=re.IGNORECASE)]

    # columns inside SELECT
    select_match = re.search(r'SELECT(.*?)FROM', sql_for_parsing, re.IGNORECASE)
    columns = []
    if select_match:
        col_part = select_match.group(1)
        raw_cols = col_part.split(',')
        for c in raw_cols:
            c = c.strip()
            # Skip if it looks like a function call
            if '(' in c and ')' in c:
                # Try to extract column from inside function (e.g., EXTRACT(MONTH FROM o.order_date))
                # Look for table.column pattern inside
                inner_match = re.search(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)', c)
                if inner_match:
                    columns.append(inner_match.group(2))
                continue
            if '.' in c:
                columns.append(c.split('.')[1])
            else:
                # Only add if it's a valid column name (not a function)
                if re.match(r'^[A-Za-z0-9_]+$', c):
                    columns.append(c)

    # clean column aliases and remove empty/function-like strings
    columns = [re.sub(r'\s+AS\s+.*', '', col, flags=re.IGNORECASE) for col in columns]
    columns = [col for col in columns if col and re.match(r'^[A-Za-z0-9_]+$', col)]

    # Also extract any prefixed columns used elsewhere (WHERE, JOIN ON, etc.)
    # e.g. c.city, o.status - but skip function calls
    prefixed = re.findall(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_\*]+)', sql_for_parsing)
    for alias, col in prefixed:
        # ignore table.* patterns here for missing-column checks
        if col == '*':
            continue
        # Only add valid column names (not function calls)
        if re.match(r'^[A-Za-z0-9_]+$', col) and col not in columns:
            columns.append(col)

    return tables, columns


def fuzzy_match(name: str, candidates: List[str]) -> Optional[str]:
    """Fuzzy match a name against candidates. Returns best match if score > 0.4."""
    name_low = name.lower()
    best = None
    best_score = 0

    for cand in candidates:
        cand_low = cand.lower()

        # Exact match
        if name_low == cand_low:
            return cand

        # Character overlap score
        char_score = sum(c1 == c2 for c1, c2 in zip(name_low, cand_low)) / max(len(cand_low), 1)

        # Substring match bonus (e.g., "customers" contains "customer" which is close to "clients")
        substring_bonus = 0
        if name_low in cand_low or cand_low in name_low:
            substring_bonus = 0.2

        # Common prefix/suffix bonus
        prefix_bonus = 0
        suffix_bonus = 0
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
        if extract_type == 'MONTH':
            return f"CAST(strftime('%m', {date_expr}) AS INTEGER)"
        elif extract_type == 'YEAR':
            return f"CAST(strftime('%Y', {date_expr}) AS INTEGER)"
        elif extract_type == 'DAY':
            return f"CAST(strftime('%d', {date_expr}) AS INTEGER)"
        else:
            # Generic conversion
            return f"strftime('%{extract_type[0]}', {date_expr})"

    # Pattern: EXTRACT(MONTH FROM o.order_date) or EXTRACT (MONTH FROM o.order_date)
    sql = re.sub(
        r'EXTRACT\s*\(\s*(\w+)\s+FROM\s+([^)]+)\s*\)',
        extract_to_strftime,
        sql,
        flags=re.IGNORECASE
    )

    return sql


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

    # Convert SQLite-incompatible syntax first
    fixed_sql = _convert_sqlite_syntax(sql)

    # We'll attempt up to N iterations to validate and auto-correct the SQL.
    # Only after exhausting all attempts will we return an error.
    max_attempts = 10

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
# HELPER FUNCTIONS (not exposed as tools)
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


# ================================================================
# TOOLS FOR AI AGENT
# ================================================================

@tool
def get_database_schema_info() -> str:
    """
    Get the complete database schema including all tables and their columns.
    Use this tool when you need to understand the database structure before writing SQL queries.
    """
    try:
        schema = get_database_schema()
        if not schema or schema == 'No tables or views found.':
            return 'Database schema is empty or unavailable. Please check database configuration.'
        return schema
    except Exception as e:
        return f"Error retrieving schema: {str(e)}"


@tool
def get_table_preview(table_name: str, limit: int = 5) -> str:
    """
    Get a preview of sample rows from a specific table.
    Use this tool to understand the data structure and sample values in a table before querying it.

    Args:
        table_name: The name of the table to preview
        limit: Maximum number of rows to return (default: 5)
    """
    try:
        rows = _get_table_preview(table_name, limit)
        if not rows:
            return f"Could not retrieve preview for table '{table_name}'. Table may not exist or is empty."

        if len(rows) == 0:
            return f"Table '{table_name}' exists but contains no rows."

        # Format the preview nicely
        lines = [f"Preview of table '{table_name}' ({len(rows)} rows):"]
        for i, row in enumerate(rows, 1):
            row_str = ', '.join([f"{k}: {v}" for k, v in row.items()])
            lines.append(f"  Row {i}: {row_str}")

        return '\n'.join(lines)
    except Exception as e:
        return f"Error retrieving table preview: {str(e)}"


@tool
def validate_sql_query(sql_query: str) -> str:
    """
    Validate and attempt to auto-correct a SQL SELECT query against the database schema.
    This tool checks table/column names and can automatically fix common issues.
    Returns validation status and any corrections made.

    Use this tool before executing queries to ensure they will work correctly.
    """
    try:
        # 1) Safety check
        ok, msg = is_safe_select_query(sql_query)
        if not ok:
            return json.dumps({
                'valid': False,
                'message': msg,
                'query': sql_query,
                'corrected_query': None
            })

        # 2) Validate and fix
        is_valid, msg, fixed_sql = validate_and_fix_sql(sql_query)

        if is_valid:
            if fixed_sql != sql_query:
                return json.dumps({
                    'valid': True,
                    'message': f'Query validated and auto-corrected: {msg}',
                    'query': sql_query,
                    'corrected_query': fixed_sql
                })
            else:
                return json.dumps({
                    'valid': True,
                    'message': 'Query is valid',
                    'query': sql_query,
                    'corrected_query': sql_query
                })
        else:
            return json.dumps({
                'valid': False,
                'message': msg,
                'query': sql_query,
                'corrected_query': fixed_sql if fixed_sql != sql_query else None
            })
    except Exception as e:
        return json.dumps({
            'valid': False,
            'message': f'Validation error: {str(e)}',
            'query': sql_query,
            'corrected_query': None
        })


@tool
def execute_database_query(sql_query: str) -> str:
    """
    Execute a SELECT or PRAGMA query against the database.
    The query will be automatically validated and corrected in the background (up to 10 attempts).
    Only returns an error if all correction attempts fail.
    Returns the query results in JSON format.

    IMPORTANT: Only SELECT and PRAGMA queries are allowed. All other SQL operations are blocked.
    This tool automatically fixes common issues like:
    - Column name mismatches (e.g., client_id -> customer_id)
    - Table name mismatches (e.g., customers -> clients)
    - SQLite syntax conversion (e.g., EXTRACT() -> strftime())
    All fixes happen automatically in the background.
    """
    # 1) Safety rule
    ok, msg = is_safe_select_query(sql_query)
    if not ok:
        return json.dumps({'error': msg, 'query': sql_query, 'results': []})

    # 2) Convert to SQLite syntax first (EXTRACT -> strftime, etc.)
    current_sql = _convert_sqlite_syntax(sql_query)

    # 2.5) Check for incomplete/malformed queries
    # Check for incomplete function calls (e.g., "EXTRACT (MONTH FROM o.o" without closing paren)
    if re.search(r'EXTRACT\s*\([^)]*$', current_sql, re.IGNORECASE):
        # Try to fix incomplete EXTRACT calls
        # Look for pattern like "EXTRACT (MONTH FROM o.o" and try to complete it
        # This is a best-effort fix
        pass  # Let validation handle it

    # 3) Automatic retry and correction loop (up to 10 attempts)
    last_error_msg = ''
    max_retries = 10
    schema = get_sqlite_schema()

    for attempt in range(1, max_retries + 1):
        # Validate and attempt to fix
        is_valid, msg, fixed_sql = validate_and_fix_sql(current_sql)

        # If validation fails due to syntax errors, try to fix common issues
        if not is_valid and 'syntax error' in msg.lower():
            # Try to fix incomplete queries
            # Check for incomplete table references (e.g., "o.o" should be "o.order_date")
            incomplete_pattern = r'(\w+)\.(\w+)?$'
            match = re.search(incomplete_pattern, fixed_sql)
            if match and not match.group(2):
                # Incomplete reference like "o." - try to infer from context
                match.group(1)
                # This is complex - skip for now, let it fail gracefully

        if is_valid:
            # Valid query found - try to execute it
            results, err = execute_query(fixed_sql)
            if not err:
                # Success! Return results (only show corrected query if it changed)
                return json.dumps({
                    'success': True,
                    'query': fixed_sql,
                    'row_count': len(results),
                    'results': results
                })
            else:
                # Execution error - try to fix based on execution error
                # Check if it's a column/table error we can fix
                if 'no such column' in err.lower() or 'no such table' in err.lower():
                    current_sql = fixed_sql  # Use the fixed SQL as base for next attempt
                    last_error_msg = f"Execution error: {err}"
                    continue
                else:
                    # Non-recoverable execution error
                    return json.dumps({'error': err, 'query': fixed_sql, 'results': []})
        else:
            # Invalid query - try to fix more aggressively
            if schema and attempt < max_retries:
                # Extract identifiers and try intelligent fixes
                tables, columns = extract_query_identifiers(current_sql)
                made_progress = False

                # FIRST: Fix table names (e.g., customers -> clients)
                for table_name in tables:
                    if table_name not in schema:
                        # Try fuzzy match
                        match = fuzzy_match(table_name, list(schema.keys()))
                        if match:
                            # Replace table name in SQL (be careful with word boundaries)
                            current_sql = re.sub(rf'\b{re.escape(table_name)}\b', match, current_sql, flags=re.IGNORECASE)
                            made_progress = True
                            LOG.info(f"Fixed table name {table_name} -> {match}")
                        else:
                            # Try substring matching (e.g., customers -> clients)
                            table_lower = table_name.lower()
                            for schema_table in schema.keys():
                                schema_lower = schema_table.lower()
                                # Check if they share significant characters
                                if (table_lower[:3] == schema_lower[:3] or
                                    table_lower[-3:] == schema_lower[-3:] or
                                        table_lower in schema_lower or schema_lower in table_lower):
                                    if len(table_name) >= 5 and len(schema_table) >= 5:
                                        current_sql = re.sub(rf'\b{re.escape(table_name)}\b', schema_table, current_sql, flags=re.IGNORECASE)
                                        made_progress = True
                                        LOG.info(f"Fixed table name {table_name} -> {schema_table} (substring match)")
                                        break

                # Re-extract after table name fixes
                tables, columns = extract_query_identifiers(current_sql)

                # Build alias -> table mapping
                alias_map: Dict[str, str] = {}
                from_join_pattern = r'(FROM|JOIN)\s+([A-Za-z0-9_]+)(?:\s+([A-Za-z0-9_]+))?'
                for m in re.findall(from_join_pattern, current_sql, flags=re.IGNORECASE):
                    tbl = m[1]
                    alias = m[2] if len(m) > 2 and m[2] else None
                    if alias:
                        alias_map[alias] = tbl
                    else:
                        alias_map[tbl] = tbl  # Table name is also its own alias

                # Try to fix column names by checking actual table schemas
                for col in columns:
                    if col == '*':
                        continue

                    # Check if column exists in any table
                    col_exists = any(col in cols for cols in schema.values())
                    if not col_exists:
                        # Try fuzzy matching across all tables
                        all_cols = []
                        for tbl_cols in schema.values():
                            all_cols.extend(tbl_cols)

                        match = fuzzy_match(col, all_cols)
                        if match:
                            # Find which table has this column
                            for tbl_name, tbl_cols in schema.items():
                                if match in tbl_cols:
                                    # Replace column name in SQL
                                    current_sql = re.sub(rf'\b{col}\b', match, current_sql, flags=re.IGNORECASE)
                                    made_progress = True
                                    break

                    # Also check prefixed columns (table.column or alias.column)
                    prefixed_pattern = rf'(\w+)\.{re.escape(col)}\b'
                    for match_obj in re.finditer(prefixed_pattern, current_sql, flags=re.IGNORECASE):
                        prefix = match_obj.group(1)
                        # Resolve alias to table name
                        actual_table = alias_map.get(prefix, prefix)
                        if actual_table in schema:
                            tbl_cols = schema[actual_table]
                            if col not in tbl_cols:
                                # Try to find similar column in this table
                                match = fuzzy_match(col, tbl_cols)

                                # Also check for common patterns (e.g., client_id -> customer_id)
                                # If column ends with _id and we're in a JOIN context, check for other _id columns
                                if not match and col.endswith('_id'):
                                    # Get all _id columns from this table
                                    id_cols = [c for c in tbl_cols if c.endswith('_id') and c != col]
                                    if id_cols:
                                        # For JOIN queries, often the foreign key has a different base name
                                        # (e.g., orders.client_id -> orders.customer_id)
                                        # If there's only one _id column besides 'id', prefer it
                                        non_id_cols = [c for c in id_cols if c != 'id']
                                        if len(non_id_cols) == 1:
                                            match = non_id_cols[0]
                                        elif len(non_id_cols) > 1:
                                            # Multiple options - use fuzzy match on the _id columns
                                            match = fuzzy_match(col, non_id_cols)

                                if match:
                                    # Replace with correct column
                                    current_sql = re.sub(
                                        rf'\b{prefix}\.{re.escape(col)}\b',
                                        f'{prefix}.{match}',
                                        current_sql,
                                        flags=re.IGNORECASE
                                    )
                                    made_progress = True
                                    LOG.info(f"Fixed column {prefix}.{col} -> {prefix}.{match}")

                if made_progress:
                    last_error_msg = msg
                    continue

                # If no progress, try using fixed_sql from validation
                if fixed_sql != current_sql:
                    current_sql = fixed_sql
                    last_error_msg = msg
                    continue

            # No more progress possible
            last_error_msg = msg

    # All attempts exhausted - return helpful error message
    schema_preview = ''
    try:
        schema = get_sqlite_schema()
        if schema:
            preview = _format_schema_preview(schema)
            schema_preview = f"\n\nDatabase schema:\n{preview}"
    except Exception:
        pass

    return json.dumps({
        'error': (
            f'Could not create a valid query after {max_retries} attempts. '
            f'Last error: {last_error_msg}. '
            f'Please improve your prompt with more specific details about which tables and columns you need. '
            f'You can use get_database_schema_info tool to see available tables and columns.'
            + schema_preview
        ),
        'query': current_sql,
        'results': []
    })
