# Merge Progress

Plan: `~/.claude/plans/compiled-enchanting-parasol.md`
Updated: 2026-07-18 | Phase: 2 | Branch: `feature/merge-mcp`

## Now

Phase 2.3/2.5 — the web frontend: vanilla ES modules at `/ui`, sidebar, tool-call chips,
streaming cursor, DOMPurify on all LLM output. Backend for it is done and tested.

## Blocked

- none

## Gate status: 5/5 green

`ruff` · `black` · `isort` · `pylint 9.78` · `mypy 0 errors` · `pytest 103/103`
Always verify with the CI-pinned linter versions (see Key facts).
Suite grew 37 -> 103 during phase 2 (agent events 24, auth 25, SSE 17).

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
- [ ] 2 Web chat + SSE
  - [x] 2.1 `chat_stream()` + `agents/events.py`; `chat()` drains it (no forked logic)
  - [x] 2.2 `POST /chat/stream` SSE; persistence in `finally` survives Stop
  - [x] 2.4 cookie session auth; browser never holds the API key
  - [ ] 2.3/2.5 frontend + UX
- [ ] 3 SQL engine port    (3.1 purify · 3.2 guard 2x · 3.3 dialect gate · 3.4 params · 3.5 tests)
- [ ] 4 MCP server         (4.1 adapter · 4.2 tools · 4.3 kube · 4.4 deploy · 4.5 auth)
- [ ] 5 LLM consolidation  (5.1 ABC · 5.2 factory · 5.3 prompt · 5.4 real stream)
- [ ] 6 Security           (#1-15)
- [ ] 7 State/cleanup/docs (7.1-7.7)

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

- 2026-07-18 — fixed RAG syntax + typing errors before Phase 1, on `fix/rag-syntax-errors`
  rather than inside the merge — keeps a 1180-line pre-existing breakage out of the merge
  diff, where it would have been indistinguishable from merge fallout.
- 2026-07-18 — kept the vector-backed `SimpleRAGPipeline.retrieve` over the lexical stub
  that shadowed it. Strictly, preserving behavior meant keeping the shadow, but the shadow
  iterates `self._documents`, which is never assigned → guaranteed AttributeError. Nothing
  calls it either way.

## Debt (must clear before done)

- [ ] lint exclusions in `pyproject.toml`, 5 tools each with own syntax, all TODO(phase-N)
      tagged: ruff/black/isort/mypy/pylint + pytest `norecursedirs` → phases 3/4/5/7.5
- [ ] `docs/legacy/` (8 MCP markdowns) consolidate              → phase 7.6
- [ ] `_legacy/mcp/` (Dockerfile, compose, config variant)      → phase 4
- [ ] re-add MCP-origin deps pinned as each feature lands: psycopg2/pymysql/pyodbc
      (phase 3), pypdf + doc parsers (phase 7.5)
- [ ] `GF_SECURITY_ADMIN_PASSWORD: admin` in docker-compose.secrets.yml:141 → phase 6
- [ ] stale `python LLM_CI/ChatGUI.py` hint in tests/fixtures/sample_database.py → phase 3
- [ ] `_legacy/` empty + CI check                        → phase 5
- [ ] simulated stream → real `stream_chat`              → phase 5.4
- [ ] upload button enabled                              → phase 7.5
- [x] ~~mypy: 124 errors~~ — cleared, gate green
- [x] ~~`agent.py` dead `rag_retriever`~~ — method deleted
- [x] ~~`SimpleRAGPipeline.ingest_website`~~ — fixed to `ingest_url`
- [ ] `cli.py` broken f-strings: bare `print(".4f")` at 6+ sites, prints the literal
      instead of the metric. Not a lint error, so no gate catches it → phase 7.3
- [ ] `OllamaRegistry` implements the async `ModelRegistry` base synchronously, so
      `CompositeRegistry.registries` must be typed `Any`. Unify the two → phase 5
- [ ] local `datasets/` dir (no `__init__.py`) shadows the HuggingFace `datasets`
      package as a namespace package → phase 6 (rename when ML extra is split out)

## Log

<!-- newest first: YYYY-MM-DD | phase | what landed | commit -->

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
