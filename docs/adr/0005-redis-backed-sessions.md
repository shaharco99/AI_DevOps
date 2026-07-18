# ADR-0005: conversation memory lives in Redis, and never on the agent

Date: 2026-07-18 · Status: accepted

## Context

`SessionManager` kept conversation memories in a process dictionary, and the
agent — a process-wide singleton — held the current memory as instance state.

The second problem was a data leak, not a scaling one: the guard was
`if session_id and not self.conversation_memory`, so once set it was never
replaced and the next user inherited the previous user's history. Reproduced
before fixing.

The first problem is that the Dockerfile runs uvicorn with `WEB_CONCURRENCY`
workers, so a user's turns land on whichever worker the balancer picks and the
conversation appears to lose its memory at random. Restarts dropped everything.

## Decision

Memory is resolved per call from `session_id` and never stored on the agent.
Storage sits behind a `SessionStore` protocol: Redis when `REDIS_URL` is set,
an in-process dict otherwise. The request's database session travels in a
`ContextVar` for the same reason — `get_agent()` used to bind the first
request's session into the singleton forever.

## Consequences

Redis was already in `docker-compose` with a healthcheck and a volume and
connected to by nothing; this is what it is for. A Redis outage degrades to
in-process memory rather than failing startup, because durable chat history
lives in Postgres regardless — the loss is conversational context, not the
transcript.

Redis stores serialised copies, so mutations need an explicit `save_session()`.
An in-process dict sees them for free, which is exactly the kind of difference
that only shows up against the real thing.
