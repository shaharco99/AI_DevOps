# Production-Readiness Report (explained simply) 🚀

Date: 2026-07-10. "Production-ready" means: **safe to run for real people, not
just on your laptop.** We checked the whole project like inspecting a house before
you move a family in — are the doors locked, does the smoke alarm work, will the
lights stay on? Below is what we found and what we fixed.

Each item is either **✅ FIXED** (done on branch `feature/production-hardening`)
or **📋 TODO** (a good idea we're recommending, not done yet).

## The big picture

The project was a great prototype — like a house that's built and pretty, but with
a few unlocked doors, no smoke alarm, and a password written on the front door. We
went around and fixed the important safety things. A few bigger renovations are
left on a to-do list.

---

## 1. The shipping box (Docker) 📦

Docker packs the app into a box so it runs the same everywhere.

- ✅ **The box was twice as big as it needed to be.** It carried heavy tools
  (compilers) it only needed while *building*, not while *running*. We now build
  in one box and ship a lighter one — it went from **969 MB down to 578 MB**.
- ✅ **Rebuilds were slow.** Changing one line of code re-downloaded *everything*.
  We reordered the steps so only what changed gets rebuilt.
- ✅ **The password was written on the box** (`devops_password`, Grafana `admin`).
  Now those come from a settings file you control, not baked in for the world.
- ✅ **No auto-restart, no size limits.** If a container crashed it stayed dead,
  and any one could eat all the computer's memory. Now they restart themselves
  and each has a memory/CPU limit.
- ✅ **"Latest" versions everywhere.** "Latest" changes without warning and can
  break you overnight. We pinned exact versions.
- ✅ **Databases were reachable by the whole network.** Now the database, cache,
  and dashboards only answer to *your* machine.

## 2. Does the app stay healthy? 🏥

- ✅ **The "am I ready?" check always lied and said yes.** So even with a dead
  database, the app kept getting visitors it couldn't serve. Now the readiness
  check actually pings the database and the AI brain, and says "not ready" (503)
  when either is down.
- ✅ **When the AI hiccuped, the app gave up instantly and returned nothing.** Now
  it politely tries again a few times (with a pause between tries) before giving
  up, and when it truly fails it says so clearly instead of returning an empty
  answer.
- ✅ **Database connections went stale and caused mystery errors.** We told the app
  to quietly test and refresh connections before using them.
- ✅ **Request logs were invisible** at the normal setting. Now you can see who's
  knocking.

## 3. The big playground (Kubernetes) 🎡

Kubernetes runs the app at scale on many computers.

- ✅ **The "front gate with a lock" (HTTPS/TLS) was described but never built.**
  The recipe mentioned a secure gate, but the actual instructions to build it were
  missing, so it never appeared. We added the missing piece — now the secure gate
  really gets built.
- ✅ **The database password was written in plain sight** inside the app's setup.
  Now it's pulled from a sealed envelope (a Kubernetes Secret).
- ✅ **The "publish a release" robot was broken in two places** and would fail.
  Both fixed.
- ✅ **The app ran as the "administrator" user** with full powers it didn't need.
  Now it runs as a limited user who can't escalate — much safer if something goes
  wrong.

## 4. Locks and guards (security) 🛡️

- ✅ **Anyone could talk to the app.** Now the important doors can require a
  password key (`X-API-Key`). It's *off* by default so the demo still works, and
  you flip it on with one setting.
- ✅ **No limit on how fast someone could hammer the app.** Now there's a speed
  limit (e.g. 30 chats a minute) so one person can't flood it.
- ✅ **Old libraries with known holes** (`cryptography`, `aiohttp`, `requests`)
  were updated to patched versions.
- 📋 **A real, live AI key is sitting in a local `.env` file.** It's not shared on
  the internet, but you should **change that key** and store keys in a proper
  vault. (Details in [security-review.md](security-review.md).)

---

## Two things we didn't touch on purpose

1. **Four files in the project don't even open** — they have typos in the code
   (`cli.py`, and three files in the `rag/` folder) that stop them from running.
   These need a separate repair; they also make the project-wide code check fail.
2. **One AI library (`langchain`) is very old** but updating it would break other
   things, so that's a bigger job for later.

## How we checked our work ✅

- All **30 small tests pass** (we added 12 new ones for the health check, the
  password door, and the retry-on-hiccup behavior).
- The Docker box **builds and is smaller**.
- The Kubernetes recipe **passes its checker** and the secure gate now shows up.
- The tidy-up tools (formatting, imports) are **clean** on everything we changed.

Want the door-by-door security walk-through in plain words? See
[security-review.md](security-review.md).
