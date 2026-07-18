# ADR-0001: ai-devops is the merge base

Date: 2026-07-18 · Status: accepted

## Context

Two projects overlapped: `ai-devops`, a FastAPI backend with a tool registry,
RAG, a production Helm chart and a strong CI matrix but no user interface at
all; and `MCP`, four disconnected subsystems with no HTTP layer, which owned a
1352-line SQL auto-correction engine, an MCP protocol server and a PyQt6 desktop
chat whose streaming and upload were both broken.

## Decision

Merge MCP into ai-devops, preserving history. ai-devops contributes the
infrastructure; MCP contributes domain logic.

## Consequences

MCP's files were relocated inside the MCP repository first, as rename-only
commits, so `git blame` survives and the merge resolved zero path collisions.
MCP's desktop GUI is retired rather than ported: it cannot serve a web backend,
and its two headline features did not work.

The alternative — a fresh repository — would have rebuilt CI, the Helm chart and
branch protection for no benefit, since ai-devops's CI was already the stronger
of the two.
