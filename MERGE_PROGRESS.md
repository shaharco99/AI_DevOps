# Merge Progress

Plan: `~/.claude/plans/compiled-enchanting-parasol.md`
Updated: 2026-07-18 | Phase: 2 | Branch: `feature/merge-mcp`

## Now

**The merge is complete.** All 8 phases done, all lint exclusions cleared.

Remaining follow-ups, none blocking:
- `OllamaRegistry` still implements the async `ModelRegistry` base synchronously
  (CLI-only code; `CompositeRegistry.registries` is typed `Any` because of it).
- `QueryRouter`/`ReflectionAgent` (plan 7.4) were not ported. `enable_reflection`
  remains declared and unread. Both default off in the plan anyway, and reflection
  doubles latency — worth measuring before building.
- CI should set `TEST_POSTGRES_URL` and `TEST_REDIS_URL` so the 14 service-backed
  tests do not silently skip there.

## Blocked

- none

## Gate status: 5/5 green

`ruff` · `black` · `isort` · `pylint 9.78` · `mypy 0 errors` · `pytest 478` (492 w/ Postgres+Redis) + 38 JS · **zero lint exclusions**
Always verify with the CI-pinned linter versions (see Key facts).
Suite grew 37 -> 478 Python + 38 JS across the merge.
JS tests: `node --test tests/js/*.test.js` (node's built-in runner, zero npm deps).

## Phases

- [x] 0 Pre-merge safety
  - [x] 0.1 commit MCP dirty tree on RAG + tag `pre-merge-snapshot` (950cefc)
  - [x] 0.2 secret sweep — clean, see Key facts
  - [x] 0.3 accept DB binaries + gitignore `*.db`
  - [x] 0.4 baseline CI — 4/5 gates green; mypy red (above)
- [x] 1 History merge — merge commit `e7cbec1`, 178 files, blame preserved
  - [x] 1.1 relocate (10 src + 12 tests/fixtures + 8 docs, all rename-only)
  - [x] 1.2 delete 6 dead modules, each verified unreferenced first
  - [x] 1.3 merge `--allow-unrelated-histories`, **0 conflicts, 0 path collisions**
  - [x] 1.4 union config: .gitignore, gitleaks + detect-secrets hooks, baseline regenerated
  - [x] 1.5 verified — see Phase 1 evidence
- [x] 2 Web chat + SSE — working UI at /ui, verified against a live server
  - [x] 2.1 `chat_stream()` + `agents/events.py`; `chat()` drains it (no forked logic)
  - [x] 2.2 `POST /chat/stream` SSE; persistence in `finally` survives Stop
  - [x] 2.4 cookie session auth; browser never holds the API key
  - [x] 2.3/2.5 frontend + UX — vanilla ESM at /ui, no build step, no vendored libs
- [x] 3 SQL engine port — 1352 -> 620 pure lines; 118 new tests; verified on real Postgres
  - [x] 3.1 purified: `validate_and_fix_sql(sql, schema)`, no module globals
  - [x] 3.2 guard runs before AND after correction
  - [x] 3.3 dialect gate — landmine confirmed real, then defused
  - [x] 3.4 NL->SQL returns (sql, params); no interpolation
  - [x] 3.5 tests ported; all phase-3 lint exclusions removed
- [x] 4 MCP server — verified with a real MCP client: handshake, tools/list, tools/call
  - [x] 4.1 adapter; MCP + REST share one registry, asserted by test
  - [x] 4.2 RCE deleted; ShellTool argv-allowlisted, off by default; cluster_overview ported
  - [x] 4.3 K8S_VERIFY_SSL was declared-but-unused; now applied, refused in production
  - [x] 4.4 second compose service, same image, port 8001, loopback-bound
  - [x] 4.5 refuses to start in production without MCP_AUTH_TOKEN
- [x] 5 LLM consolidation — one abstraction; `_legacy/` deleted; real streaming live
  - [x] 5.1 messages-first ABC; chat/stream_chat abstract, generate inherited
  - [x] 5.2 `get_llm_service()` -> `LLMFactory`; anthropic_service deleted
  - [x] 5.3 system prompt ported to `prompts/system/devops_assistant_v2.0.md`
  - [x] 5.4 real token deltas; placeholder chunking removed
- [x] 6 Security — all 15 items closed; verified by building the real image
  - [x] 6a fail-closed production config; /metrics behind auth
  - [x] 6b LLM01 fencing: separate message + delimiters + marker stripping
  - [x] 6c LLM08 tool budget; `max_tool_iterations` was declared, never read
  - [x] 6d hash-pinned lockfile, ML extras split out, CycloneDX SBOM attested
- [x] 7 State/cleanup/docs
  - [x] 7.1 Redis session store; verified across processes
  - [x] 7.2 cross-user conversation bleed fixed (reproduced first)
  - [x] 7.3 8 dead methods, 12 broken cli prints, Grafana password, Chroma, datasets/
  - [x] 7.5 loaders rewritten + `POST /rag/ingest`; upload button live
  - [x] 7.6 docs consolidated · [x] 7.7 five ADRs in `docs/adr/`

## Key facts (verified 2026-07-18)

- MCP merge source = branch `RAG`, strictly ahead of `main` (0/12). No reconciliation.
- MCP `.env` never committed, and contains no credentials (Ollama config + paths only).
  detect-secrets on the tree = 2 false positives; credential-pattern scan across all 546
  history objects = 0 hits. No rotation, no history rewrite.
- `DB/database.db` 0B, `Tests_DB.db` 8KB → accepted, not purged.
- ai-devops deps already `==` pinned; missing piece is a hash lockfile.
- **RAG was entirely dead**, not merely misconfigured: 4 files had syntax errors since
  f00ee1d, so `import ai_devops_assistant.rag` raised and agent.py logged "RAG pipeline
  not available". Fixed in e6c31c2 + c98f56c. The Chroma `chroma_db_impl` issue the plan
  predicted is still UNVERIFIED — it was masked by the earlier import failure. Check in
  Phase 6.
- Lint tooling: CI pins `ruff==0.1.11`, but a local venv had 0.15.11 and reported ~30 extra
  findings. Always verify gates with the pinned versions.

## Phase 1 evidence (zero behavior change)

Measured on the merged tree, compared against the pre-merge baseline:

| Check | Result |
|---|---|
| Path collisions | **0** — set comparison of both file lists before merging |
| Merge conflicts | **0** |
| File count | 138 + 40 = **178**, set-compared: nothing extra, nothing missing |
| Blame | `git blame sql_correction.py` shows `LLM_CI/database_tools.py`, orig. author/date |
| MCP history | 44 commits reachable; merge commit has 2 parents |
| mypy | **124 errors / 28 files — identical to baseline**, merge added zero |
| pylint | 9.78/10 (baseline 9.77) |
| ruff / black / isort | pass; 68 files still checked (unchanged), `agent.py` still linted |
| pytest | 37 collected, 37 pass; **0** collected from `tests/mcp` |
| App | `create_app()` builds, **16 routes — identical surface** |
| Merged code inert | no MCP module in `sys.modules` after `create_app()` |

## Decisions

<!-- deviations from the plan only; format: date — decision — why -->

- 2026-07-18 — bumped the web stack (fastapi 0.115.6, starlette 0.41.3, httpx 0.28.1,
  uvicorn 0.34.0, python-dotenv 1.2.2). fastmcp's transitive mcp SDK needs httpx>=0.28,
  which breaks starlette 0.36's TestClient. Shipping unsatisfied pins was the alternative.
  Full suite verified on the new stack before the pins changed.

- 2026-07-18 — the plan's example of the engine repairing `customers` -> `clients` is not
  achievable: that is a semantic mapping, and difflib fails identically. It repairs typos,
  plurals and case. Refusing an unmatched name is safer than silently querying another
  table, so the error path was improved instead (names + suggestion + schema preview).
- 2026-07-18 — deleted `tests/mcp` and `tests/fixtures` rather than porting. They test the
  connection-bound API (`call_tool`/`_original_func`, module globals,
  `execute_database_query`) that no longer exists. 118 new tests cover more ground than
  their 69.

- 2026-07-18 — frontend renders markdown to DOM nodes instead of the planned
  marked -> DOMPurify -> innerHTML. No innerHTML anywhere, so XSS is structurally
  impossible rather than filtered, and three vendored libraries disappear. Cost: a
  markdown subset, not full CommonMark.
- 2026-07-18 — added a dependency-free `package.json` (type:module only) so
  `node --test` can import the frontend sources. No node_modules, no lockfile.

- 2026-07-18 — fixed RAG syntax + typing errors before Phase 1, on `fix/rag-syntax-errors`
  rather than inside the merge — keeps a 1180-line pre-existing breakage out of the merge
  diff, where it would have been indistinguishable from merge fallout.
- 2026-07-18 — kept the vector-backed `SimpleRAGPipeline.retrieve` over the lexical stub
  that shadowed it. Strictly, preserving behavior meant keeping the shadow, but the shadow
  iterates `self._documents`, which is never assigned → guaranteed AttributeError. Nothing
  calls it either way.

## Debt

All merge debt cleared: every `TODO(phase-N)` lint exclusion is gone and the five
gates run over the whole tree. See "Now" for non-blocking follow-ups.

## Log

<!-- newest first: YYYY-MM-DD | phase | what landed | commit -->

- 2026-07-18 | 7 | loaders, /rag/ingest, ADRs; exclusions cleared (+29) | c73a464
- 2026-07-18 | 7 | session bleed fixed, Redis store, dead code (+19) | b039178
- 2026-07-18 | 6 | fail-closed config, LLM01 fencing, lockfile (+61 tests) | 5683dcb
- 2026-07-18 | 5 | messages-first providers; _legacy deleted (+57 tests) | 54b8daf
- 2026-07-18 | 4 | MCP server + ShellTool; RCE deleted (+82 tests) | edea77a
- 2026-07-18 | 3 | SQL engine ported (+118 tests, real-PG verified) | 965f0ba
- 2026-07-18 | 2 | web UI at /ui (+16 py, +38 js tests) | f0601e0
- 2026-07-18 | 2 | SSE endpoint POST /chat/stream (+17 tests) | 6dc5dc6
- 2026-07-18 | 2 | cookie session auth (+25 tests) | 5a254f2
- 2026-07-18 | 2 | chat_stream() + events (+24 tests) | e2eb8f1
- 2026-07-18 | – | **mypy 124 -> 0; all 5 gates green** | 081a1cc,78ef815,5f624ef
- 2026-07-18 | 1 | time-boxed lint exclusions, 5 tools | da2c12f
- 2026-07-18 | 1 | union config + regenerated secrets baseline | b51a7e8
- 2026-07-18 | 1 | **MCP merged, 0 conflicts, history preserved** | e7cbec1
- 2026-07-18 | 1 | MCP-side: relocate, delete dead, drop configs | f62355c..a46d1c2
- 2026-07-18 | 0 | ruff/black/isort green + RAG bugs they exposed | c98f56c
- 2026-07-18 | 0 | repaired 4 unparseable files; RAG imports again | e6c31c2
- 2026-07-18 | 0 | MCP: snapshot commit + tag, `*.db` ignored | 950cefc (MCP repo)
- 2026-07-18 | 0 | plan approved, progress tracker created | –
