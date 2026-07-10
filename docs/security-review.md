# Security Review (explained simply) 🔒

Date: 2026-07-10. This is a "where could bad input do harm?" review. Think of the
app as a house: a **sink** is any place where something from outside (a user's
message, a query, an ID) gets *used* to do something powerful — run a database
query, call another computer, open a file. Bad guys look for a sink where they
can sneak something nasty through. We walked to every sink and checked the locks.

## The short version

Most doors are already locked well. Two need attention, and a few small things
are worth tidying. Nothing here is an open front door — but two are windows left
unlatched.

| # | Where | How bad | Locked? |
| --- | --- | --- | --- |
| 1 | SQL tool runs raw text | Medium | 🟡 Partly — uses a "banned words" list (weaker than an allow-list) |
| 2 | CI tool builds a URL from an unchecked ID | Medium | 🔴 No — the ID needs checking first |
| 3 | AI model download with no fixed version | Low–Med | 🔴 No — a swapped model could sneak in later |
| 4 | Prompt templates don't escape HTML | Low | 🟢 Fine here (prompts aren't web pages) |
| 5 | Server listens on "all doors" (0.0.0.0) | Low | 🟢 Expected inside a container |
| 6 | Log search & metrics query | — | ✅ Safe — already use proper locks |

---

## 1. The SQL tool: a bouncer with a "banned names" list 🟡

**File:** `ai_devops_assistant/tools/sql_tool.py`

**What happens:** you send a database query as text, and the tool runs it with
`text(query)`. That's the sink — raw text becoming a real database command.

**The lock today:** before running, a bouncer checks the query. It only allows
queries that start with `SELECT`, and it rejects any that contain scary words
(`DROP`, `DELETE`, `UPDATE`, …), comment marks (`--`, `/* */`), and a few classic
attack patterns.

**Why it's only *partly* locked:** this is a **deny-list** ("say no to these bad
words"). Deny-lists are like a bouncer with a photo of every troublemaker — if
someone new shows up, or wears a disguise, they get in. An **allow-list** ("only
these exact shapes of query are allowed") is much stronger. Also, the row `limit`
is applied *after* the database already did all the work, so a heavy query can
still tire out the database even if only a few rows come back.

**Fix ideas (not applied yet — flagging for your call):**

- Prefer a real read-only database role/connection so the database itself refuses
  writes, instead of trusting the word-filter.
- Push the `LIMIT` into the SQL so the database stops early.
- Longer term, move to an allow-list of query shapes.

Good news: this is deliberately a demoed feature ("look, it blocks bad queries!"),
and SELECT-only + no comments already stops the common attacks.

## 2. The CI pipeline tool: an address built from an unchecked ID 🔴

**File:** `ai_devops_assistant/tools/pipeline_tool.py`

**What happens:** to look up a build, the tool glues a web address together like
`.../builds/{build_id}/timeline`, where `build_id` came from the request. That
glued-together address is the sink — it decides *which computer and page* we call.

**Why it's risky:** nobody checks that `build_id` is actually a plain number. If
someone passes something sneaky (like `../../secret-endpoint`), the address could
point somewhere we didn't intend — this family of bug is called SSRF / path
injection ("make the server fetch a page of *my* choosing").

**Fix idea:** before using it, make sure `build_id` is only digits (or URL-encode
it). One line of validation closes this window.

## 3. Downloading an AI model with no fixed version 🔴

**File:** `ai_devops_assistant/ml/finetuning.py` (several `from_pretrained(...)` calls)

**What happens:** the code downloads a model by name but doesn't pin a **revision**
(an exact version). It's like ordering "the usual" from a bakery — if someone
swaps the recipe tomorrow, you eat the new one without noticing. A bad actor who
takes over that model's page could feed you a tampered model later.

**Fix idea:** pin a `revision="<commit-or-tag>"` on each `from_pretrained` call so
you always get the exact version you reviewed.

## 4. Prompt templates don't auto-escape 🟢 (just noting)

**File:** `ai_devops_assistant/agents/prompt_manager.py`

Bandit flags that Jinja2 isn't escaping HTML. That warning matters when you build
**web pages** (to stop XSS). Here Jinja2 only builds **text prompts** for the AI,
not HTML shown in a browser, so it's not a real XSS hole. Leave as-is; just don't
reuse this renderer to build HTML later.

## 5. Listening on "all doors" (0.0.0.0) 🟢 (expected)

**File:** `ai_devops_assistant/config/settings.py`

The server binds to `0.0.0.0`, meaning "accept visitors on every network door."
Inside a container that's normal and needed. The real protection is *outside* —
in `docker-compose.yml` we now bind the database, cache, and dashboards to
`127.0.0.1` (your machine only), and in Kubernetes the network policy limits who
can knock.

## 6. Two sinks that are already safe ✅

- **Log search** (`tools/log_tool.py`): it searches with
  `ApplicationLog.message.ilike(f"%{query}%")`. Even though there's an f-string,
  SQLAlchemy hands the whole thing to the database as a **bound value** (a sealed
  envelope), not as runnable SQL. No injection possible.
- **Metrics query** (`tools/metrics_tool.py`): the PromQL text is sent to
  Prometheus as `params={"query": query}`, which gets safely URL-encoded, and
  Prometheus only *reads* — it can't change anything.

---

## What we recommend doing next

1. **Validate `build_id`** in the pipeline tool (quick, closes finding #2).
2. **Pin model revisions** in `ml/finetuning.py` (finding #3).
3. **Give the SQL tool a read-only database role** and push `LIMIT` into SQL
   (hardens finding #1 beyond the word-filter).

None of these block the demo working today — they're the difference between
"locked for a demo" and "locked for the real world."
