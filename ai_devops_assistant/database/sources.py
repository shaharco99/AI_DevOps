"""Named external databases the SQL tool can query.

The app's own database is reached through ``database/session.py``; this module is
for the *other* ones — a production Oracle, a legacy SQL Server — that the agent
reads but never owns.

Three properties matter here and each is enforced below rather than left to the
caller:

- **Read-only.** These are other teams' production systems. Every engine is
  opened with autocommit so nothing can be left in an open transaction, and the
  SQL tool's SELECT-only guard still applies on top.
- **Async drivers only.** The tool runs on the async engine, so a sync driver
  (``oracle+oracledb``, ``mssql+pyodbc``) would raise deep inside SQLAlchemy at
  query time. It is rejected at load time instead, where the error can name the
  fix.
- **Lazily connected.** A configured-but-unreachable source must not stop the
  app from starting; the failure belongs to the query that needs it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

# The app's own database. Reserved so a source cannot shadow it.
DEFAULT_SOURCE = "default"

# Drivers whose sync counterpart is the one people reach for first. Used only to
# make the error message actionable.
_ASYNC_EQUIVALENT = {
    "oracle+oracledb": "oracle+oracledb_async",
    "oracle+cx_oracle": "oracle+oracledb_async",
    "mssql+pyodbc": "mssql+aioodbc",
    "mssql+pymssql": "mssql+aioodbc",
    "postgresql+psycopg2": "postgresql+asyncpg",
    "mysql+pymysql": "mysql+aiomysql",
}

# Suggested driver when a URL names a dialect but no driver at all.
_DEFAULT_ASYNC_DRIVER = {
    "oracle": "oracle+oracledb_async",
    "mssql": "mssql+aioodbc",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
}


class SourceConfigError(ValueError):
    """SQL_SOURCES is malformed. Raised at load time, never at query time."""


def _parse_sources(raw: str) -> dict[str, str]:
    """Parse the SQL_SOURCES JSON blob into {name: url}."""
    raw = (raw or "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceConfigError(f"SQL_SOURCES is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise SourceConfigError("SQL_SOURCES must be a JSON object of {name: url}")

    sources: dict[str, str] = {}
    for name, url in parsed.items():
        if not isinstance(url, str):
            raise SourceConfigError(f"SQL_SOURCES[{name!r}] must be a connection URL string")
        if name == DEFAULT_SOURCE:
            raise SourceConfigError(
                f"{DEFAULT_SOURCE!r} is reserved for the application's own database; "
                "give the external source a different name"
            )
        _validate_async_driver(name, url)
        sources[name] = url
    return sources


def _validate_async_driver(name: str, url: str) -> None:
    """Reject sync drivers at load time, naming the async replacement."""
    try:
        drivername = make_url(url).drivername
    except Exception as exc:  # noqa: BLE001 - surfaced with the source name attached
        raise SourceConfigError(f"SQL_SOURCES[{name!r}] is not a valid URL: {exc}") from exc

    if "+" not in drivername:
        example = _DEFAULT_ASYNC_DRIVER.get(drivername, "oracle+oracledb_async")
        raise SourceConfigError(
            f"SQL_SOURCES[{name!r}] uses {drivername!r}, which names no driver, so "
            f"SQLAlchemy picks the sync default. Say it explicitly, e.g. {example!r}"
        )

    try:
        dialect = make_url(url).get_dialect()
    except ModuleNotFoundError as exc:
        raise SourceConfigError(
            f"SQL_SOURCES[{name!r}] needs the {drivername!r} driver, which is not installed: {exc}"
        ) from exc

    if not getattr(dialect, "is_async", False):
        suggestion = _ASYNC_EQUIVALENT.get(drivername)
        hint = f" Use {suggestion!r} instead." if suggestion else ""
        raise SourceConfigError(f"SQL_SOURCES[{name!r}] uses the sync driver {drivername!r}.{hint}")


def _engine_kwargs(url: str) -> dict[str, Any]:
    """Pool and connect settings for an external source."""
    kwargs: dict[str, Any] = {
        "pool_size": settings.SQL_SOURCE_POOL_SIZE,
        "pool_timeout": settings.SQL_SOURCE_POOL_TIMEOUT,
        # These are remote systems that get restarted and firewalled without
        # telling us; a stale pooled connection is the normal failure here.
        "pool_pre_ping": True,
        "pool_recycle": settings.DATABASE_POOL_RECYCLE,
        # Nothing this engine runs is ever meant to write, so never hold a
        # transaction open on someone else's production database.
        "isolation_level": "AUTOCOMMIT",
        "echo": settings.DATABASE_ECHO,
    }

    drivername = make_url(url).drivername
    timeout = settings.SQL_SOURCE_CONNECT_TIMEOUT
    # Connect-timeout is spelled differently per driver, and passing the wrong
    # key is a TypeError at connect time rather than something ignored.
    if drivername.startswith("oracle"):
        kwargs["connect_args"] = {"tcp_connect_timeout": timeout}
    elif drivername.startswith("mssql"):
        kwargs["connect_args"] = {"timeout": timeout}
    elif drivername.startswith("postgresql"):
        kwargs["connect_args"] = {"timeout": timeout}
    return kwargs


class SourceRegistry:
    """Lazily-built async engines, one per configured source."""

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self._urls: dict[str, str] = sources if sources is not None else _parse_sources(
            settings.SQL_SOURCES
        )
        self._engines: dict[str, AsyncEngine] = {}

    @property
    def names(self) -> list[str]:
        """Configured source names, not including the app's own database."""
        return sorted(self._urls)

    def __contains__(self, name: str) -> bool:
        return name in self._urls

    def engine(self, name: str) -> AsyncEngine:
        """The engine for ``name``, created on first use.

        Raises:
            KeyError: If the source is not configured. The message lists what is,
                because the caller is usually an LLM that guessed the name.
        """
        if name not in self._urls:
            known = ", ".join(self.names) or "none configured"
            raise KeyError(f"Unknown SQL source {name!r}. Configured sources: {known}")

        engine = self._engines.get(name)
        if engine is None:
            engine = create_async_engine(self._urls[name], **_engine_kwargs(self._urls[name]))
            self._engines[name] = engine
            logger.info(
                "Opened SQL source %r (%s)", name, make_url(self._urls[name]).render_as_string()
            )
        return engine

    async def dispose(self) -> None:
        """Close every engine that was actually opened."""
        for name, engine in self._engines.items():
            await engine.dispose()
            logger.info("Closed SQL source %r", name)
        self._engines.clear()


# Process-wide registry. Parsing happens at import so a malformed SQL_SOURCES
# fails at startup rather than on the first query that needs it.
registry = SourceRegistry()
