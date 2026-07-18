# Merge Progress

Plan: `~/.claude/plans/compiled-enchanting-parasol.md`
Updated: 2026-07-18 | Phase: 0 | Branch: `feature/production-hardening` (pre-merge)

## Now

Phase 0.1 — commit MCP's dirty tree on branch `RAG`, tag `pre-merge-snapshot`.

## Blocked

- none

## Phases

- [ ] 0 Pre-merge safety
  - [ ] 0.1 commit MCP dirty tree on RAG + tag `pre-merge-snapshot`
  - [ ] 0.2 gitleaks sweep + `.env` live-secret check
  - [ ] 0.3 accept DB binaries + gitignore `*.db`
  - [ ] 0.4 baseline CI green
- [ ] 1 History merge      (1.1 relocate · 1.2 delete dead · 1.3 merge · 1.4 configs · 1.5 CI green)
- [ ] 2 Web chat + SSE     (2.1 chat_stream · 2.2 endpoint · 2.3 frontend · 2.4 auth · 2.5 UX)
- [ ] 3 SQL engine port    (3.1 purify · 3.2 guard 2x · 3.3 dialect gate · 3.4 params · 3.5 tests)
- [ ] 4 MCP server         (4.1 adapter · 4.2 tools · 4.3 kube · 4.4 deploy · 4.5 auth)
- [ ] 5 LLM consolidation  (5.1 ABC · 5.2 factory · 5.3 prompt · 5.4 real stream)
- [ ] 6 Security           (#1-15)
- [ ] 7 State/cleanup/docs (7.1-7.7)

## Key facts (verified 2026-07-18)

- MCP merge source = branch `RAG`, strictly ahead of `main` (0/12). No reconciliation.
- MCP `.env` never committed → no history rewrite needed.
- `DB/database.db` 0B, `Tests_DB.db` 8KB → accepted, not purged.
- ai-devops deps already `==` pinned; missing piece is a hash lockfile.

## Decisions

<!-- deviations from the plan only; format: date — decision — why -->

## Debt (must clear before done)

- [ ] lint exclusions: `_legacy/`, `sql_correction.py`   → phases 3/5
- [ ] `_legacy/` empty + CI check                        → phase 5
- [ ] simulated stream → real `stream_chat`              → phase 5.4
- [ ] upload button enabled                              → phase 7.5

## Log

<!-- newest first: YYYY-MM-DD | phase | what landed | commit -->

- 2026-07-18 | 0 | plan approved, progress tracker created | –
