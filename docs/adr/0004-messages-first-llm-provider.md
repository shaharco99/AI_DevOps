# ADR-0004: LLMFactory is the single provider abstraction, messages-first

Date: 2026-07-18 · Status: accepted

## Context

There were two provider abstractions: an if-chain in `llm_service` choosing
between `OllamaService` and `AnthropicService`, and the richer
`LLMProvider`/`LLMFactory` in `multi_llm` that the chat path never used. They
also disagreed on shape — one took messages, the other a prompt string.

## Decision

One abstraction, `LLMFactory`, and `chat(messages)`/`stream_chat(messages)` are
the abstract methods. `generate(prompt)` is an inherited convenience that wraps
a single user message.

## Consequences

Messages-first is not a style preference. Anthropic and OpenAI are natively
messages-based, and flattening a conversation into one string destroys the
system/user boundary — which is exactly the boundary that keeps retrieved
documents and tool output from being read as instructions. The prompt-injection
fencing in ADR-0005's sibling work is expressed entirely in terms of that
boundary, so a prompt-string interface would have made it impossible to write.

Providers raise `LLMProviderError` rather than returning `""`. An empty string
is indistinguishable from a model that legitimately produced no text, so a total
outage used to surface as a blank assistant bubble with nothing in the logs.

MCP's `get_llm_provider` was discarded rather than merged: it prompted
interactively with `input()`, called `getpass`, appended API keys to `.env` at
runtime and ran `pip install` from application code. Only its curated system
prompt was worth keeping.
