"""Request-scoped database session, carried in a ContextVar.

Tools need the caller's ``AsyncSession``, but the tool registry and the agent are
process-wide singletons, so an instance attribute on either is shared by every
concurrent request. Binding a session there meant the *first* request's session
was reused forever — by then usually closed, and never the caller's.

A ContextVar is the right shape for this: asyncio copies the context per task, so
each request sees its own value with no locking and no plumbing through every
call signature.

The session is set by the request dependency (api/dependencies.py) and read by
the tools that need it.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from sqlalchemy.ext.asyncio import AsyncSession

_current_session: ContextVar[AsyncSession | None] = ContextVar("current_db_session", default=None)


def set_current_session(session: AsyncSession | None) -> Token:
    """Bind a session to the current context.

    Returns:
        A token for reset_current_session(), so nesting restores the previous
        value rather than clearing it.
    """
    return _current_session.set(session)


def reset_current_session(token: Token) -> None:
    """Restore the session bound before the matching set_current_session()."""
    _current_session.reset(token)


def get_current_session() -> AsyncSession | None:
    """The session for this request, or None outside a request."""
    return _current_session.get()
